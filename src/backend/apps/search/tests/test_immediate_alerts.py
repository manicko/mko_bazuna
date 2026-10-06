"""
Unit tests for the immediate-alert delivery bridge (EXT-002).

Covers:
- One Bot constructed per batch (not per message); session.close once in finally.
- asyncio.gather return_exceptions=True isolates failures (siblings proceed).
- 429 TelegramRetryAfter backoff honored and retry attempted.
- _run_send catches Exception and logs with a stack trace; a failure no longer
  escapes into a Future nobody retrieves (09-API-013).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from concurrent.futures import Future
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import (
    AiogramError,
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramServerError,
)

from apps.core.enums import AdStatus
from apps.core.utils.sanitize import mask_telegram_id
from apps.search.models import SavedSearch
from conftest import create_test_ad

pytestmark = [pytest.mark.unit]


def _payload(chat_id: int = 1) -> dict:
    """Minimal payload dict matching the shape _build_payload returns."""
    return {"chat_id": chat_id, "text": "test message", "reply_markup": None}


# ---------------------------------------------------------------------------
# Bot reuse — one Bot per batch, session closed once
# ---------------------------------------------------------------------------


class TestBotReuse:
    """One Bot is constructed per _send_payloads invocation, not per message."""

    @pytest.mark.asyncio
    async def test_one_bot_constructed_once_per_batch(self) -> None:
        """Bot is created once (not per message); session.close called once."""
        payloads = [_payload(1), _payload(2), _payload(3)]

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock()
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import _send_payloads

            await _send_payloads("test-token", payloads)

            # Exactly one Bot constructed per batch (not per message).
            assert mock_bot_cls.call_count == 1
            # One send_message call per payload.
            assert mock_bot.send_message.await_count == 3
            # session.close called exactly once in finally.
            assert mock_bot.session.close.await_count == 1

    @pytest.mark.asyncio
    async def test_session_closed_even_when_send_fails(self) -> None:
        """session.close is always called via finally, even on dead-letter."""
        payloads = [_payload(42)]

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(
                side_effect=TelegramForbiddenError(
                    message="blocked by user",
                    method=MagicMock(),
                )
            )
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import _send_payloads

            await _send_payloads("test-token", payloads)

            assert mock_bot.session.close.await_count == 1
            assert mock_bot.send_message.await_count == 1


# ---------------------------------------------------------------------------
# return_exceptions isolation
# ---------------------------------------------------------------------------


class TestGatherIsolation:
    """return_exceptions=True prevents sibling cancellation on failure."""

    @pytest.mark.asyncio
    async def test_permanent_failure_does_not_cancel_siblings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A TelegramForbiddenError on one payload does not block siblings."""
        payloads = [_payload(1), _payload(2), _payload(3)]

        attempted: list[int] = []

        def fake_send_message(**kwargs: object) -> None:
            attempted.append(int(kwargs["chat_id"]))
            if int(kwargs["chat_id"]) == 2:
                raise TelegramForbiddenError(
                    message="chat not found",
                    method=MagicMock(),
                )

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(side_effect=fake_send_message)
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import _send_payloads

            await _send_payloads("test-token", payloads)

            # All three payloads attempted despite the failure on chat 2.
            assert sorted(attempted) == [1, 2, 3]
            assert mock_bot.session.close.await_count == 1

    @pytest.mark.asyncio
    async def test_unhandled_exception_does_not_cancel_siblings(self) -> None:
        """A non-AiogramError escaping _send is captured by return_exceptions."""
        payloads = [_payload(1), _payload(2), _payload(3)]

        attempted: list[int] = []

        def fake_send_message(**kwargs: object) -> None:
            attempted.append(int(kwargs["chat_id"]))
            if int(kwargs["chat_id"]) == 2:
                raise RuntimeError("unexpected")

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(side_effect=fake_send_message)
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import _send_payloads

            # return_exceptions=True: gather must not raise the RuntimeError.
            await _send_payloads("test-token", payloads)

            assert sorted(attempted) == [1, 2, 3]
            assert mock_bot.session.close.await_count == 1


# ---------------------------------------------------------------------------
# 429 retry-after backoff
# ---------------------------------------------------------------------------


class TestRetryAfterBackoff:
    """TelegramRetryAfter (429) honors retry_after for backoff and retries."""

    @pytest.mark.asyncio
    async def test_429_retry_after_honored(self) -> None:
        """retry_after is used as backoff; send_message retried after sleep."""
        payloads = [_payload(42)]

        retry_exc = TelegramRetryAfter(
            message="too many requests",
            method=MagicMock(),
            retry_after=2,
        )

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(
                side_effect=[retry_exc, None]
            )
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import _send_payloads

            with patch(
                "apps.search.services.immediate_alerts.asyncio.sleep",
                new=AsyncMock(),
            ) as mock_sleep:
                await _send_payloads("test-token", payloads)

            # Backoff sleep honored with retry_after value (2.0 seconds).
            mock_sleep.assert_awaited_once_with(2.0)
            # Retry attempted: 2 total send_message calls.
            assert mock_bot.send_message.await_count == 2

    @pytest.mark.asyncio
    async def test_transient_error_uses_capped_backoff(self) -> None:
        """TelegramServerError triggers retry with _BACKOFF_BASE backoff."""
        payloads = [_payload(99)]

        server_exc = TelegramServerError(
            message="internal server error",
            method=MagicMock(),
        )

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(
                side_effect=[server_exc, None]
            )
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import (
                _BACKOFF_BASE,
                _send_payloads,
            )

            with patch(
                "apps.search.services.immediate_alerts.asyncio.sleep",
                new=AsyncMock(),
            ) as mock_sleep:
                await _send_payloads("test-token", payloads)

            # Retry uses _BACKOFF_BASE (capped backoff, not retry_after).
            mock_sleep.assert_awaited_once_with(_BACKOFF_BASE)
            assert mock_bot.send_message.await_count == 2

    @pytest.mark.asyncio
    async def test_retry_failure_swallowed_and_logged(self) -> None:
        """If the retry also raises, it is logged and does not propagate."""
        payloads = [_payload(7)]

        retry_exc = TelegramRetryAfter(
            message="too many requests",
            method=MagicMock(),
            retry_after=1,
        )
        second_exc = TelegramForbiddenError(
            message="blocked",
            method=MagicMock(),
        )

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(
                side_effect=[retry_exc, second_exc]
            )
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import _send_payloads

            with patch(
                "apps.search.services.immediate_alerts.asyncio.sleep",
                new=AsyncMock(),
            ):
                # Must not raise — retry failure is caught by the inner
                # except AiogramError handler and logged.
                await _send_payloads("test-token", payloads)

            assert mock_bot.send_message.await_count == 2
            assert mock_bot.session.close.await_count == 1

    @pytest.mark.asyncio
    async def test_429_retry_after_is_capped(self) -> None:
        """A huge Telegram retry_after is clamped to RETRY_AFTER_CEILING (Q8)."""
        payloads = [_payload(42)]

        retry_exc = TelegramRetryAfter(
            message="too many requests",
            method=MagicMock(),
            retry_after=300,
        )

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(side_effect=[retry_exc, None])
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import (
                RETRY_AFTER_CEILING,
                _send_payloads,
            )

            with patch(
                "apps.search.services.immediate_alerts.asyncio.sleep",
                new=AsyncMock(),
            ) as mock_sleep:
                await _send_payloads("test-token", payloads)

            # The mandated 300 s is clamped to the 30 s ceiling.
            mock_sleep.assert_awaited_once_with(30.0)
            assert RETRY_AFTER_CEILING == 30.0
            # Retry still attempted: two send_message calls.
            assert mock_bot.send_message.await_count == 2


# ---------------------------------------------------------------------------
# Hostile seller markup (09-API-006)
# ---------------------------------------------------------------------------


_HOSTILE_TITLE = 'Selling <b>bold</b> & <a href="http://evil.example">x</a>'
_HOSTILE_EVIL = "<a href=\"http://evil.example\">"


class TestHostileMarkupEscaped:
    """Seller-authored text is escaped in the immediate-alert body (09-API-006).

    Built from a MagicMock ad so the test is pure (``build_alert_message`` needs no
    database). The RED evidence against the unfixed tree was: the raw
    ``<b>bold</b>`` and the injected ``<a href="http://evil.example">`` were present
    verbatim in the body — one seller's markup becomes live in every subscriber's
    chat and Telegram rejects an unparseable entity set as a permanent
    ``TelegramBadRequest`` with no retry.
    """

    def _hostile_ad(self) -> MagicMock:
        ad = MagicMock()
        ad.get_title.return_value = _HOSTILE_TITLE
        ad.city.get_name.return_value = "Testgrad"
        ad.price_amount = 0
        ad.price_currency = "EUR"
        ad.get_absolute_url.return_value = "https://example.com/ads/1/"
        return ad

    def test_builder_escapes_seller_markup(self) -> None:
        """A hostile title produces no live seller markup in the message body."""
        from apps.search.services.immediate_alerts import build_alert_message

        saved_search = MagicMock()
        saved_search.unsubscribe_token = "tok"

        text, _keyboard = build_alert_message(self._hostile_ad(), saved_search, locale="en")

        # The seller's tags are escaped, so none of their markup is live.
        assert "<b>bold</b>" not in text
        assert _HOSTILE_EVIL not in text
        assert "&lt;b&gt;bold&lt;/b&gt;" in text
        assert "&amp;" in text
        # The structural tags the builder owns are still live.
        assert text.startswith("<b>")
        assert 'href="https://example.com/ads/1/"' in text

    @pytest.mark.asyncio
    async def test_retry_send_site_carries_escaped_text(self) -> None:
        """The escaped text reaches send_message on BOTH the initial and retry sends."""
        from apps.search.services.immediate_alerts import (
            _send_payloads,
            build_alert_message,
        )

        saved_search = MagicMock()
        saved_search.unsubscribe_token = "tok"
        text, keyboard = build_alert_message(
            self._hostile_ad(), saved_search, locale="en"
        )
        payloads = [{"chat_id": 1, "text": text, "reply_markup": keyboard}]

        retry_exc = TelegramRetryAfter(
            message="too many requests",
            method=MagicMock(),
            retry_after=1,
        )

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(side_effect=[retry_exc, None])
            mock_bot.session.close = AsyncMock()

            with patch(
                "apps.search.services.immediate_alerts.asyncio.sleep",
                new=AsyncMock(),
            ):
                await _send_payloads("test-token", payloads)

        assert mock_bot.send_message.await_count == 2
        # Both the initial and the retry send carried the escaped text.
        sent_texts = [
            call.kwargs["text"]
            for call in mock_bot.send_message.await_args_list
        ]
        assert len(sent_texts) == 2
        for sent in sent_texts:
            assert "<b>bold</b>" not in sent
            assert _HOSTILE_EVIL not in sent


# ---------------------------------------------------------------------------
# _run_send exception narrowing
# ---------------------------------------------------------------------------

class TestRunSendExceptionNarrowing:
    """_run_send contains any exception and logs it with a stack trace.

    The previous class docstring stated "_run_send catches AiogramError, not
    bare Exception", and ``test_non_aiogram_error_propagates`` asserted that a
    ``RuntimeError`` propagated. Both encoded the 09-API-013 defect as intended
    behaviour: a non-``AiogramError`` reached the unretrieved ``Future`` and was
    lost with no log line. ``_run_send`` now catches ``Exception`` and logs it.
    """

    def test_aiogram_error_caught_and_logged(self) -> None:
        """AiogramError from _send_payloads is caught (not propagated)."""
        with patch(
            "apps.search.services.immediate_alerts._send_payloads",
            new=AsyncMock(side_effect=AiogramError("network down")),
        ):
            from apps.search.services.immediate_alerts import _run_send

            # Must not raise — AiogramError is caught and logged.
            _run_send([])

    def test_non_aiogram_error_is_logged_with_stack_trace(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A RuntimeError is logged at ERROR with a traceback — it does not escape.

        The old ``test_non_aiogram_error_propagates`` asserted
        ``pytest.raises(RuntimeError)`` here. That documented the defect:
        ``deliver_immediate_alerts`` discards the ``Future``, so an escaping
        error was stored where nobody read it and the batch was lost silently.
        """
        with patch(
            "apps.search.services.immediate_alerts._send_payloads",
            new=AsyncMock(side_effect=RuntimeError("unexpected")),
        ):
            from apps.search.services.immediate_alerts import _run_send

            with caplog.at_level(logging.ERROR):
                # Must not raise: the error is contained, not propagated.
                _run_send([])

        records = [
            r for r in caplog.records if r.levelno == logging.ERROR
        ]
        assert records, "a non-AiogramError dispatch must leave an ERROR log"
        assert any(r.exc_info is not None for r in records), (
            "the failure must be logged with a stack trace (logger.exception)"
        )
        assert "unexpected" in caplog.text


# ---------------------------------------------------------------------------
# Dispatch observability + backpressure (09-API-013)
# ---------------------------------------------------------------------------


class _ImmediateFutureExecutor:
    """Run each submission inline and return a real, already-resolved Future.

    Mirrors the production contract the caller relies on: ``submit`` returns a
    ``concurrent.futures.Future`` so the done-callback can retrieve its outcome.
    """

    def submit(self, fn, *args):  # noqa: ANN001, ANN201
        future: Future = Future()
        try:
            fn(*args)
        except BaseException as exc:  # noqa: BLE001
            future.set_exception(exc)
        else:
            future.set_result(None)
        return future


class TestDispatchFailureIsRetrievable:
    """A failed dispatch leaves a retrievable ERROR log with the payload count."""

    def test_done_callback_logs_failure_with_payload_count(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A non-AiogramError batch failure is retrieved, not lost in the Future."""
        from apps.search.services import immediate_alerts

        monkeypatch.setattr(
            immediate_alerts, "_executor", _ImmediateFutureExecutor()
        )
        monkeypatch.setattr(
            immediate_alerts,
            "_run_send",
            lambda payloads: (_ for _ in ()).throw(RuntimeError("payload builder")),
        )
        monkeypatch.setattr(immediate_alerts, "_in_flight_batches", 0)

        # Drive _on_send_finished directly with a resolved-with-exception Future
        # carrying the payload count, exactly as deliver_immediate_alerts binds it.
        future: Future = Future()
        future.set_exception(RuntimeError("payload builder"))

        with caplog.at_level(logging.ERROR):
            immediate_alerts._on_send_finished(3, future)

        records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert records, "a failed dispatch must leave a retrievable ERROR log"
        assert any("3" in r.getMessage() for r in records), (
            "the ERROR log must carry the payload count"
        )
        assert any(r.exc_info is not None for r in records), (
            "the failure must be logged with a stack trace"
        )

    def test_done_callback_decrements_counter_on_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The in-flight counter cannot leak on an exception path."""
        from apps.search.services import immediate_alerts

        monkeypatch.setattr(immediate_alerts, "_in_flight_batches", 1)
        future: Future = Future()
        future.set_exception(RuntimeError("boom"))

        immediate_alerts._on_send_finished(1, future)

        assert immediate_alerts._in_flight_batches == 0


class TestBackpressureSheds:
    """Above the in-flight threshold the dispatch is skipped with a WARNING."""

    @pytest.mark.django_db
    @pytest.mark.integration
    def test_backlog_above_threshold_skips_and_warns(
        self,
        seller,
        buyer,
        category,
        city,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A saturated backlog issues no outbound send and logs a WARNING."""
        from apps.search.services import immediate_alerts

        submitted: list[list] = []
        monkeypatch.setattr(
            immediate_alerts,
            "_executor",
            type(
                "_Recorder",
                (),
                {"submit": lambda self, fn, *a: submitted.append(a)},
            )(),
        )
        # Pretend the backlog is already at the threshold.
        monkeypatch.setattr(
            immediate_alerts,
            "_in_flight_batches",
            immediate_alerts._MAX_IN_FLIGHT_BATCHES,
        )

        ad = create_test_ad(
            seller, category, city, title="Красный велосипед",
            status=AdStatus.PUBLISHED,
        )
        SavedSearch.objects.create(user=buyer, is_active=True)

        with caplog.at_level(logging.WARNING):
            immediate_alerts.deliver_immediate_alerts(ad.id)

        assert submitted == [], "a shed dispatch must not reach the executor"
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any(f"ad {ad.id}" in r.getMessage() for r in warnings), (
            "the WARNING must name the ad"
        )
        assert any(
            str(immediate_alerts._MAX_IN_FLIGHT_BATCHES) in r.getMessage()
            for r in warnings
        ), "the WARNING must name the in-flight count/threshold"
        # The counter is untouched by a shed dispatch.
        assert (
            immediate_alerts._in_flight_batches
            == immediate_alerts._MAX_IN_FLIGHT_BATCHES
        )


# ---------------------------------------------------------------------------
# Worker-side invariant pin (09-API-013 / 09-NEW-01)
# ---------------------------------------------------------------------------

_IMPORT_GRAPH_PROBE = """
import sys

import django

django.setup()
print("SETUP:" + str("apps.search.services.immediate_alerts" in sys.modules))
import apps.moderation.signals  # noqa: F401

print("SIGNALS:" + str("apps.search.services.immediate_alerts" in sys.modules))
"""


class TestWorkerSideInvariant:
    """The executor must be built post-fork, i.e. not during ``django.setup()``.

    ``preload_app = True`` means ``django.setup()`` runs in the gunicorn master
    before workers fork. Worker-side-ness of the pool holds ONLY because
    ``apps/moderation/signals.py`` imports ``immediate_alerts`` lazily inside
    ``transaction.on_commit``. Hoisting that import to module level, or adding
    ``immediate_alerts`` to ``apps/search/services/__init__.py``, would build
    the executor in the master and reproduce "rows written, delivered_at NULL,
    no send, no log" (09-NEW-01). A pytest process has already imported the
    module by test time, so the assertion must run in a fresh interpreter.
    """

    def test_module_absent_from_setup_import_graph(self) -> None:
        """``django.setup()`` and ``import moderation.signals`` do not pull it in."""
        from django.conf import settings as django_settings

        backend_dir = str(django_settings.BASE_DIR)
        project_src = str(django_settings.BASE_DIR.parent)
        env = dict(os.environ)
        env.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (project_src, backend_dir, existing) if p
        )
        result = subprocess.run(
            [sys.executable, "-c", _IMPORT_GRAPH_PROBE],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "SETUP:False" in result.stdout, (
            "immediate_alerts was imported by django.setup() - the executor "
            f"would be built in the gunicorn master\n{result.stdout}\n{result.stderr}"
        )
        assert "SIGNALS:False" in result.stdout, (
            "importing apps.moderation.signals pulled in immediate_alerts - the "
            "lazy import inside _deliver() was hoisted\n"
            f"{result.stdout}\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# build_alert_message keyboard callback_data (CR9 / AL-002)
# ---------------------------------------------------------------------------


class TestBuildAlertMessageKeyboard:
    """The per-ad alert keyboard carries an unsubscribe inline button.

    The button's ``callback_data`` binds the search's opaque unsubscribe token
    so a tap can route the deep-link back to the bot (AL-002).
    """

    def test_build_alert_message_unsubscribe_callback(self) -> None:
        """Button callback_data is ``unsub:<saved_search.unsubscribe_token>``."""
        from apps.search.services.immediate_alerts import (
            UNSUB_CALLBACK_PREFIX,
            build_alert_message,
        )

        ad = MagicMock()
        ad.get_title.return_value = "Test Ad"
        ad.city.get_name.return_value = "Тестград"
        ad.price_amount = 0
        ad.price_currency = "EUR"
        ad.get_absolute_url.return_value = "https://example.com/ads/1/"

        saved_search = MagicMock()
        saved_search.unsubscribe_token = "opaque_token_123"

        _text, keyboard = build_alert_message(ad, saved_search, locale="en")

        button = keyboard.inline_keyboard[0][0]
        assert button.callback_data == (
            f"{UNSUB_CALLBACK_PREFIX}{saved_search.unsubscribe_token}"
        )
        assert button.callback_data is not None
        assert button.callback_data.startswith("unsub:")
        assert button.callback_data.endswith("opaque_token_123")


# ---------------------------------------------------------------------------
# Identifier masking in the failure-branch logs (06-PII-102)
# ---------------------------------------------------------------------------


class TestFailureBranchLogsMaskIdentifier:
    """Both failure branches mask the chat_id in the log and keep it in the send.

    The log argument is masked through ``mask_telegram_id`` while the transport
    argument (what ``send_message`` receives) stays the real integer. The mask
    is asserted through ``mask_telegram_id`` itself — never on its width, prefix
    or hash shape — because it is a keyed HMAC whose value is not fixed.
    """

    _RAW_CHAT_ID = 987654321

    @pytest.mark.asyncio
    async def test_permanent_failure_branch_masks_log_keeps_send(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Forbidden -> forever dead-lettered: log masked, send real."""
        payload = _payload(self._RAW_CHAT_ID)

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(
                side_effect=TelegramForbiddenError(
                    message="blocked by user",
                    method=MagicMock(),
                )
            )
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import _send_payloads

            with caplog.at_level(logging.WARNING):
                await _send_payloads("test-token", [payload])

        # The formatted log message does not contain the raw Telegram id.
        assert str(self._RAW_CHAT_ID) not in caplog.text
        # The mask produced by the production helper is what was logged.
        assert mask_telegram_id(self._RAW_CHAT_ID) in caplog.text
        # The transport value is untouched: the sender received the real id.
        sent_call = mock_bot.send_message.await_args
        assert sent_call is not None
        sent_kwargs = sent_call.kwargs
        assert sent_kwargs["chat_id"] == self._RAW_CHAT_ID
        # The payload the sender consumed still carries the real id.
        assert payload["chat_id"] == self._RAW_CHAT_ID

    @pytest.mark.asyncio
    async def test_post_retry_failure_branch_masks_log_keeps_send(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Transient then retry fails -> log masked, both sends real."""
        payload = _payload(self._RAW_CHAT_ID)

        retry_exc = TelegramRetryAfter(
            message="too many requests",
            method=MagicMock(),
            retry_after=1,
        )
        second_exc = TelegramForbiddenError(
            message="blocked",
            method=MagicMock(),
        )

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(
                side_effect=[retry_exc, second_exc]
            )
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import _send_payloads

            with (
                caplog.at_level(logging.WARNING),
                patch(
                    "apps.search.services.immediate_alerts.asyncio.sleep",
                    new=AsyncMock(),
                ),
            ):
                await _send_payloads("test-token", [payload])

        # Both the primary and the retry failure logs are masked.
        assert str(self._RAW_CHAT_ID) not in caplog.text
        assert mask_telegram_id(self._RAW_CHAT_ID) in caplog.text
        # Both send attempts received the real integer, unmasked.
        attempted = [
            call.kwargs["chat_id"]
            for call in mock_bot.send_message.await_args_list
        ]
        assert attempted == [self._RAW_CHAT_ID, self._RAW_CHAT_ID]
