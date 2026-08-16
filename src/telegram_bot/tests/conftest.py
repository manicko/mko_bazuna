"""
Test fixtures for telegram_bot tests.

Bootstraps Django + aiogram test infrastructure with shared DB fixtures,
enabling handler tests against the real PostgreSQL ORM (two-process contract).
"""

import hashlib
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

# ---------------------------------------------------------------------------
# aiogram infrastructure
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def bot() -> Bot:
    """Create a Bot instance with the configured token for testing.

    The token is read from Django settings (loaded by the root conftest).
    Tests never call the Telegram API, so a placeholder token suffices.
    """
    return Bot(token=settings.BOT_TOKEN)


@pytest.fixture
def dp() -> Dispatcher:
    """Create a Dispatcher with the same middleware and routers as production.

    This replicates the setup from ``telegram_bot.main()`` so that handler
    tests exercise the full pipeline (middleware -> router -> handler).
    """
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    from telegram_bot.handlers import ad_create_router, login_router
    from telegram_bot.middlewares import AccountStateMiddleware

    dp.message.middleware(AccountStateMiddleware())  # pyright: ignore[reportAbstractUsage]
    dp.include_router(login_router)
    dp.include_router(ad_create_router)

    return dp


# ---------------------------------------------------------------------------
# Django ORM fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user() -> Any:
    """Create a test user."""
    from apps.users.models import User

    user, _ = User.objects.get_or_create(
        telegram_id=900000100,
        defaults={
            "chat_id": 900000100,
            "username": "test_user",
            "first_name": "Test",
            "last_name": "User",
        },
    )
    return user


@pytest.fixture
def login_token_factory() -> Callable[..., Awaitable[tuple[str, Any]]]:
    """Factory fixture for creating LoginToken instances.

    Returns a callable that accepts an optional ``raw_token`` string
    and returns ``(raw_token, LoginToken)``.
    """
    from apps.users.models import LoginToken

    async def _create(
        raw_token: str = "abc123_def456_ghi789_jkl012_mno345",
    ) -> tuple[str, Any]:
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        token = await sync_to_async(LoginToken.objects.create)(
            token_hash=token_hash,
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        return raw_token, token

    return _create