"""
Tests for process_preview — original_language detection from Telegram user locale.

Verifies that the ad's ``original_language`` is derived from
``message.from_user.language_code`` via ``LanguageLocale.from_code``, with a
fallback to ``BOSNIAN`` when the code is missing or unsupported.

The full ``process_preview`` → ``update_ad_and_moderate`` → ``auto_moderate``
pipeline is exercised against the real PostgreSQL ORM.  ``translate_all_languages``
is mocked to avoid hitting the Google Translate API.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow, pytest.mark.integration, pytest.mark.concurrent]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def seller_id() -> int:
    """Create a minimal seller user and return its ID."""
    from apps.users.models import User

    user = User.objects.create(
        telegram_id=900000200,
        chat_id=900000200,
        username="lang_test_user",
        first_name="Lang",
        last_name="Tester",
        password="x",
    )
    return user.id


@pytest.fixture
def permissive_criteria(monkeypatch) -> None:
    """Monkeypatch moderation criteria so auto_moderate passes trivially."""
    _permissive = (1, 200, 1, 2000, False, 0, 10, (), 100, 0)
    monkeypatch.setattr(
        "apps.moderation.services.auto_moderation._get_cached_criteria",
        lambda: _permissive,
    )
    monkeypatch.setattr(
        "apps.moderation.services.auto_moderation._validate_max_ads_per_user",
        lambda user_id, max_ads: True,
    )
    monkeypatch.setattr(
        "apps.moderation.services.auto_moderation._is_duplicate_title",
        lambda title, user_id, ad_id, threshold: False,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_message(language_code: str | None) -> MagicMock:
    """Build a mock Telegram message for the preview/confirm step."""
    user_mock = MagicMock()
    user_mock.language_code = language_code
    message = MagicMock()
    message.text = "confirm"
    message.from_user = user_mock
    message.answer = AsyncMock()
    return message


def _build_state(data: dict) -> MagicMock:
    """Build a mock FSMContext backed by the given state data."""
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data)
    state.clear = AsyncMock()
    return state


async def _mock_translate(text: str, target_locales: list[str]) -> dict[str, str]:
    """Return deterministic translations without hitting the real API."""
    return {loc: f"{text}-{loc}" for loc in target_locales}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProcessPreviewLanguageDetection:
    """Tests for original_language detection in process_preview."""

    @pytest.mark.asyncio
    async def test_original_language_detected_from_user(
        self, seller_id: int, permissive_criteria: None
    ) -> None:
        """Ad original_language is set from the Telegram user's language_code."""
        from telegram_bot.handlers.ad_create import create_draft_ad, process_preview

        ad = await create_draft_ad(user_id=seller_id)

        state = _build_state({
            "ad_id": ad.id,
            "title": "Valid Title",
            "description": "Valid description text for the ad.",
            "price_amount": 100,
            "price_currency": "EUR",
            "photos": [],
            "user_id": seller_id,
        })

        message = _build_message("en-US")

        with patch(
            "telegram_bot.handlers.ad_create.translate_all_languages",
            _mock_translate,
        ):
            await process_preview(message, state)

        from apps.ads.models import Ad

        saved = await sync_to_async(Ad.objects.get)(id=ad.id)
        assert saved.original_language == "en"

    @pytest.mark.asyncio
    async def test_original_language_falls_back_to_bosnian(
        self, seller_id: int, permissive_criteria: None
    ) -> None:
        """Ad original_language falls back to BOSNIAN when language_code is None."""
        from telegram_bot.handlers.ad_create import create_draft_ad, process_preview

        ad = await create_draft_ad(user_id=seller_id)

        state = _build_state({
            "ad_id": ad.id,
            "title": "Valid Title",
            "description": "Valid description text for the ad.",
            "price_amount": 100,
            "price_currency": "EUR",
            "photos": [],
            "user_id": seller_id,
        })

        message = _build_message(None)

        with patch(
            "telegram_bot.handlers.ad_create.translate_all_languages",
            _mock_translate,
        ):
            await process_preview(message, state)

        from apps.ads.models import Ad

        saved = await sync_to_async(Ad.objects.get)(id=ad.id)
        assert saved.original_language == "bs"
