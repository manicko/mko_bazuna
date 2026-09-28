"""
Performance guard: AccountStateMiddleware resolves the acting user ONCE.

Before the fix, ``__call__`` issued up to three independent ``User.objects.get``
lookups per update (interaction gate, publish gate, FSM user_id backfill).
This module pins the post-fix fan-out at exactly one ``User`` SELECT per
update, across every update shape.

It deliberately does NOT use ``CaptureQueriesContext`` / ``assertNumQueries``:
the middleware's ORM work runs inside ``@sync_to_async`` on asgiref's single
worker thread, which owns a *different* ``BaseDatabaseWrapper`` than the test
thread (see conftest.py "Leaked worker-thread connection cleanup").  A
test-thread capture records zero queries and passes vacuously.  Instead we
capture SQL through an ``execute_wrapper`` installed on every connection
Django opens, on any thread.

The ``>= 1`` floor inside the bound assertion is what makes a broken (vacuous)
capture fail loudly instead of passing silently.
"""

import contextlib
import itertools
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message
from asgiref.sync import sync_to_async
from django.db import connections
from django.db.backends.signals import connection_created
from django.utils import timezone

from apps.users.models import User
from conftest import make_user
from telegram_bot.middlewares import AccountStateMiddleware

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))

_BASE_CHAT_ID = 900000400

_USER_TABLE_QUOTED: str = f'"{User._meta.db_table}"'  # '"users_user"'

_USER_SELECT_BOUND: int = 1

_SINK_LOCK = threading.Lock()

_next_update_id = itertools.count(700)


def _make_message_update(chat_id: int, text: str = "") -> Any:
    """Construct a real aiogram Update wrapping a Message from a test user."""
    from aiogram.types import Chat, Message, Update, User as TelegramUser

    user = TelegramUser(id=chat_id, first_name="Test", is_bot=False)
    return Update(
        update_id=next(_next_update_id),
        message=Message(
            message_id=1,
            date=timezone.now(),
            chat=Chat(id=chat_id, type="private"),
            from_user=user,
            text=text,
        ),
    )


def _make_callback_update(chat_id: int, callback_data: str = "test_action") -> Any:
    """Construct a real aiogram Update wrapping a CallbackQuery from a test user."""
    from aiogram.types import (
        CallbackQuery,
        Chat,
        Message,
        Update,
        User as TelegramUser,
    )

    user = TelegramUser(id=chat_id, first_name="Test", is_bot=False)
    bot = TelegramUser(id=777000, first_name="MkoBazunaBot", is_bot=True)
    msg = Message(
        message_id=1,
        date=timezone.now(),
        chat=Chat(id=chat_id, type="private"),
        from_user=bot,
    )
    return Update(
        update_id=next(_next_update_id),
        callback_query=CallbackQuery(
            id="cb_test",
            from_user=user,
            message=msg,
            chat_instance="-1",
            data=callback_data,
        ),
    )


def _make_mock_fsm_context(data: dict[str, Any] | None = None) -> MagicMock:
    """Build a mock FSMContext that simulates FSM state."""
    state = MagicMock()
    if data is None:
        data = {}
    state.get_data = AsyncMock(return_value=dict(data))
    state.update_data = AsyncMock()
    return state


def _is_user_select(sql: str) -> bool:
    """True if the SQL is an ORM SELECT against the User table."""
    return sql.lstrip().upper().startswith("SELECT") and _USER_TABLE_QUOTED in sql


def _count_user_selects(captured: list[str]) -> int:
    """Count ORM SELECTs against the User table in the captured SQL."""
    return sum(1 for sql in captured if _is_user_select(sql))


@contextmanager
def _capture_sql_on_all_threads() -> Iterator[list[str]]:
    """
    Record every ORM-issued SQL statement executed on ANY thread.

    CaptureQueriesContext / assertNumQueries cannot be used here: the
    middleware's ORM work runs inside ``@sync_to_async`` on asgiref's single
    worker thread, which owns a different ``BaseDatabaseWrapper`` than the
    test thread (see conftest.py "Leaked worker-thread connection
    cleanup").  A test-thread capture records nothing and passes vacuously.

    This installs an ``execute_wrapper`` on every connection Django opens,
    on any thread, for the window's duration.  ``execute_wrappers`` is
    consulted on every ``CursorWrapper.execute``, and ``connection_created``
    fires again on every reconnect — which is what makes a worker-thread
    connection opened inside the window get covered.

    The caller must close the worker-thread connection from within the worker
    thread at the top of the window (see the test body) so it is reopened
    inside the window and fires ``connection_created``.  Without that, a
    worker connection reused across parametrized cases within one process
    would never reconnect in-window and the capture would be vacuous.

    Yields:
        The list the captured SQL strings are appended to.
    """
    sink: list[str] = []
    installed: list[Any] = []

    def _record(execute, sql, params, many, context):
        with _SINK_LOCK:
            sink.append(sql)
        return execute(sql, params, many, context)

    def _on_created(sender, connection, **kwargs):
        with _SINK_LOCK:
            connection.execute_wrappers.append(_record)
        installed.append(connection)

    connection_created.connect(_on_created)
    # Also cover a connection that already existed before the window opened
    # (cheap insurance; under the bot conftest's autouse connection reaping
    # this is expected to be a no-op).
    _on_created(None, connections["default"])
    try:
        yield sink
    finally:
        connection_created.disconnect(_on_created)
        for connection in installed:
            with contextlib.suppress(ValueError):
                connection.execute_wrappers.remove(_record)


# Each case: how to build the update, the FSM data, and how to seed the user.
# ``user_kwargs=None`` means the chat_id is NOT registered (unregistered user).
_CASES: dict[str, dict[str, Any]] = {
    "message_fsm_user_id_present": {
        "callback": False,
        "text": "",
        "fsm": {"user_id": 123},
        "user_kwargs": {},
    },
    "message_fsm_empty": {
        "callback": False,
        "text": "",
        "fsm": {},
        "user_kwargs": {},
    },
    "post_fsm_user_id_present": {
        "callback": False,
        "text": "/post",
        "fsm": {"user_id": 123},
        "user_kwargs": {},
    },
    "post_fsm_empty": {
        "callback": False,
        "text": "/post",
        "fsm": {},
        "user_kwargs": {},
    },
    "callback_fsm_empty": {
        "callback": True,
        "text": "",
        "fsm": {},
        "user_kwargs": {},
    },
    "post_unregistered_fsm_empty": {
        "callback": False,
        "text": "/post",
        "fsm": {},
        "user_kwargs": None,
    },
    "banned_user_post": {
        "callback": False,
        "text": "/post",
        "fsm": {},
        "user_kwargs": {"is_banned": True},
    },
}


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", sorted(_CASES))
async def test_user_select_count_per_update_shape(
    shape: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exactly one User SELECT is emitted per update, for every shape."""
    case = _CASES[shape]
    chat_id = _BASE_CHAT_ID + sorted(_CASES).index(shape)

    if case["callback"]:
        update = _make_callback_update(chat_id)
    else:
        update = _make_message_update(chat_id, case["text"])

    handler = AsyncMock(return_value="proceed")
    mock_answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", mock_answer)

    state = _make_mock_fsm_context(case["fsm"])
    data: dict[str, Any] = {"state": state}

    # NOTE: user setup and the middleware invocation must run INSIDE the
    # capture window.  Both execute via ``sync_to_async`` on asgiref's shared
    # worker thread, which owns its own BaseDatabaseWrapper.  We first close
    # that worker connection (from within the worker thread itself) so it is
    # deterministically reopened inside the window, firing ``connection_created``
    # and getting the execute_wrapper installed on the very connection the
    # middleware's ORM work will reuse.
    with _capture_sql_on_all_threads() as captured:
        await sync_to_async(lambda: connections["default"].close())()
        if case["user_kwargs"] is not None:
            await sync_to_async(make_user)(chat_id, **case["user_kwargs"])
        await AccountStateMiddleware()(handler, update, data)

    count = _count_user_selects(captured)
    annotated = "\n".join(
        f"  {'[USER SELECT]' if _is_user_select(s) else '[other]      '} {s}"
        for s in captured
    )

    assert 1 <= count <= _USER_SELECT_BOUND, (
        f"shape={shape} captured {count} User SELECTs "
        f"(bound <= {_USER_SELECT_BOUND}):\n{annotated}"
    )
    assert count == 1, (
        f"shape={shape} expected exactly one User SELECT:\n{annotated}"
    )

    user_selects = [s for s in captured if _is_user_select(s)]
    assert "chat_id" in user_selects[0], (
        f"shape={shape} the User SELECT must filter on chat_id, got:\n{user_selects[0]}"
    )
