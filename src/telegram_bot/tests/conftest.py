"""
Test fixtures for telegram_bot tests.

Bootstraps Django + aiogram test infrastructure with shared DB fixtures,
enabling handler tests against the real PostgreSQL ORM (two-process contract).
"""

import hashlib
import threading
from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from asgiref.sync import sync_to_async
from apps.categories.models import Category
from apps.locations.models import City
from apps.users.models import User
from django.conf import settings
from django.db import connections
from django.db.backends.signals import connection_created
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

    from telegram_bot.handlers import ad_create_router, alerts_router, login_router
    from telegram_bot.middlewares import AccountStateMiddleware

    dp.message.middleware(AccountStateMiddleware())  # pyright: ignore[reportAbstractUsage]
    dp.include_router(login_router)
    dp.include_router(ad_create_router)
    dp.include_router(alerts_router)

    return dp


# ---------------------------------------------------------------------------
# Django ORM fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def user() -> Any:
    """Create a test user."""
    from apps.users.models import User

    user, _ = await sync_to_async(User.objects.get_or_create)(
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


@pytest.fixture
def seller() -> User:
    """Create a seller user for ad-fixture composition.

    Uses telegram_id 900 000 100 to match the bot test-suite convention.
    Note: the ``user`` fixture above also uses this ID — no single test
    requests both.
    """
    return User.objects.create(
        telegram_id=900000100,
        chat_id=900000100,
        password="x",
    )


@pytest.fixture
def category() -> Category:
    """Create a leaf category for ad fixtures."""
    return Category.objects.create(
        name="Test Category",
        slug="test-category",
    )


@pytest.fixture
def city() -> City:
    """Create a city for ad fixtures."""
    return City.objects.create(
        country_code="ME",
        name="Test City",
        region="Test Region",
        slug="test-city",
    )


# ---------------------------------------------------------------------------
# Leaked worker-thread connection cleanup
#
# Bot handlers run inside ``@sync_to_async`` (asgiref 3.12, default
# ``thread_sensitive=True``). With no parent ``AsyncToSync`` wrapper, asgiref
# parks them on its shared single-worker thread, which lives in a separate
# thread-local context and therefore gets its OWN PostgreSQL backend (Django
# ``ConnectionHandler`` is thread-local when ``thread_critical=False``).
#
# Django's ``TransactionTestCase``/``TestCase`` teardown only closes the
# connection that belongs to the thread running the test. The worker-thread
# backend is never closed: it stays open (possibly ``idle in transaction``)
# across tests. With ``django_db(transaction=True)`` (bot tests) the next
# test's ``TRUNCATE ... CASCADE`` demands ``ACCESS EXCLUSIVE`` locks on every
# table while a leaked worker backend still holds row/table locks from the
# ``ads <-> categories`` cross-table triggers (see ``pg_trigger.sql``), an
# intermittent deadlock.
#
# Fix: register every connection Django opens (any thread) via the
# ``connection_created`` signal and close them after each test. Closing a
# ``BaseDatabaseWrapper`` issues a clean network Close (server-side ROLLBACK),
# releasing locks and resetting ``self.connection`` to None so the next use
# reconnects. ``pg_terminate_backend`` is deliberately avoided: it kills the
# server-side process but leaves Django's wrapper pointing at a dead socket
# (non-None), so the framework skips reconnect and raises "connection is
# closed" / "connection is lost".
# ---------------------------------------------------------------------------

_all_connections: set[Any] = set()
_all_connections_lock = threading.Lock()


def _register_connection(connection: Any, **kwargs: Any) -> None:
    """Track every DB connection Django opens, on any thread."""
    with _all_connections_lock:
        _all_connections.add(connection)


connection_created.connect(_register_connection)


def _close_all_thread_connections() -> None:
    """Close every tracked Django connection (main thread + worker threads)."""
    with _all_connections_lock:
        conns = list(_all_connections)
        _all_connections.clear()
    for _c in conns:
        try:
            _c.close()
        except Exception:
            pass
    # Also close the current thread's connection (in case it escaped tracking).
    connections.close_all()


@pytest.fixture(autouse=True)
def _reap_worker_connections() -> Iterator[None]:
    """Close sync_to_async worker-thread connections after each bot test.

    Runs after the test body (and after pytest-django's own rollback/TRUNCATE),
    terminating any worker backend that still holds trigger locks so it cannot
    collide with the next test's transaction boundary.
    """
    yield
    _close_all_thread_connections()


@pytest.fixture(autouse=True, scope="session")
def _reap_stale_backends_session() -> Iterator[None]:
    """Close any DB connection left open past per-test teardown (e.g. opened during collection/DB setup)."""
    _close_all_thread_connections()
    yield
    _close_all_thread_connections()