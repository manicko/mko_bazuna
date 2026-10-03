"""Bot-level failure branches for ``process_preview`` (AD-016).

Before AD-016 the bot had no test at all for ``process_preview``'s failure
branch, and a gone draft was reported as a moderation failure and then
destroyed the dialog via ``state.clear()``.  The recovery branch now names three
distinct non-content outcomes, each with its own accurate reply:

- ``DRAFT_GONE`` — the draft row no longer existed;
- ``INVALID_TRANSITION`` — the row existed but the state machine refused the
  transition (it is REJECTED/DELETED, not expired);
- ``PHOTO_UNAVAILABLE`` — the draft still exists; a staged photo file was
  reaped.

All three keep the FSM data and **re-point** ``ad_id`` at a fresh draft (the
typed dialog is the only remaining copy).  ``PHOTO_UNAVAILABLE`` additionally
clears the stale photo list and returns the seller to the photos step, because
re-confirming with photo keys whose files are gone loops forever.

A genuine content failure still clears the state and renders the moderation
message (the fix must not make the bot non-recoverable either way).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.enums import AdStatus

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.xdist_group("bot_concurrent"),
]

# The exact, source-defined replies.  Pinned here so a silent reword is caught;
# the catalogs' non-empty ru/bs coverage is guarded repo-wide by
# ``test_i18n_completeness.py`` (no per-string duplication here).
_DRAFT_GONE_REPLY = (
    "Your draft was no longer available, so it was replaced with a fresh one. "
    "Press confirm again to submit."
)
_INVALID_TRANSITION_REPLY = (
    "Your ad could not be submitted from its current state. A fresh draft was "
    "prepared — press confirm again to submit."
)
_PHOTO_UNAVAILABLE_REPLY = (
    "One of your photos is no longer available. A fresh draft was prepared — "
    "please upload the missing photo again, then send 'done'."
)


def _build_message(text: str = "confirm", language_code: str | None = "en-US"):
    user_mock = MagicMock()
    user_mock.language_code = language_code
    user_mock.id = 900000100
    user_mock.username = None
    user_mock.first_name = "Test"
    user_mock.last_name = "User"
    message = MagicMock()
    message.text = text
    message.from_user = user_mock
    message.answer = AsyncMock()
    return message


def _build_state(data: dict) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data)
    state.clear = AsyncMock()
    state.update = AsyncMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    return state


async def _mock_translate(text: str, target_locales: list[str]) -> dict[str, str]:
    return {loc: f"{text}-{loc}" for loc in target_locales}


def _preview_data(seller, category, city, **overrides) -> dict:
    """Build the FSM data a preview confirm carries."""
    data = {
        "ad_id": 999_999_999,
        "title": "Naslov oglasa",
        "description": "Opis oglasa dovoljne dužine za test.",
        "price_amount": 100,
        "price_currency": "EUR",
        "photos": [],
        "user_id": seller.id,
        "category_id": category.id,
        "city_id": city.id,
    }
    data.update(overrides)
    return data


class TestProcessPreviewOutcomes:
    """``process_preview`` branches on the named ``SubmitAdOutcome``."""

    @pytest.mark.asyncio
    async def test_draft_gone_repoints_state_to_a_fresh_draft(
        self, seller, category, city
    ) -> None:
        """``DRAFT_GONE`` keeps the FSM data and re-points ``ad_id``.

        The seller's preview dialog must survive a reaped/deleted draft: the
        handler creates a fresh DRAFT and updates ``ad_id`` so the next
        ``confirm`` targets a live row instead of looping against a dead one.
        """
        from telegram_bot.handlers.ad_create import process_preview

        data = _preview_data(seller, category, city)  # absent id → DRAFT_GONE
        state = _build_state(data)
        message = _build_message()

        with patch(
            "telegram_bot.handlers.ad_create.submit.translate_all_languages",
            _mock_translate,
        ):
            await process_preview(message, state)

        state.clear.assert_not_awaited()
        state.update.assert_awaited_once()
        new_ad_id = state.update.await_args.args[0]["ad_id"]
        assert new_ad_id != 999_999_999

        from asgiref.sync import sync_to_async

        from apps.ads.models import Ad

        ad = await sync_to_async(Ad.objects.get)(id=new_ad_id)
        assert ad.status == AdStatus.DRAFT
        assert ad.user_id == seller.id

    @pytest.mark.asyncio
    async def test_draft_gone_reply_is_its_own_string_not_a_content_blame(
        self, seller, category, city
    ) -> None:
        """The ``DRAFT_GONE`` reply names the cause and does not blame content."""
        from telegram_bot.handlers.ad_create import process_preview

        data = _preview_data(seller, category, city)
        state = _build_state(data)
        message = _build_message()

        with patch(
            "telegram_bot.handlers.ad_create.submit.translate_all_languages",
            _mock_translate,
        ):
            await process_preview(message, state)

        rendered = str(message.answer.await_args.args[0])
        assert rendered == _DRAFT_GONE_REPLY
        # It must not be the moderation blame, nor the raw service reason.
        assert "moderation" not in rendered.lower()
        assert "Ad not found" not in rendered

    @pytest.mark.asyncio
    async def test_each_non_content_outcome_renders_its_own_message(
        self, seller, category, city
    ) -> None:
        """Each outcome renders a distinct, accurate reply.

        ``DRAFT_GONE`` vs ``INVALID_TRANSITION`` vs ``PHOTO_UNAVAILABLE`` must
        not collapse onto one string; none of them may claim the draft "was
        deleted" (false for ``PHOTO_UNAVAILABLE``, which never reaches the
        transaction, and misleading for ``INVALID_TRANSITION``, whose row is
        REJECTED/DELETED).
        """
        from apps.ads.services.submission import (
            SubmitAdOutcome,
            SubmitAdResult,
        )
        from telegram_bot.handlers.ad_create import process_preview

        expected = {
            SubmitAdOutcome.DRAFT_GONE: _DRAFT_GONE_REPLY,
            SubmitAdOutcome.INVALID_TRANSITION: _INVALID_TRANSITION_REPLY,
            SubmitAdOutcome.PHOTO_UNAVAILABLE: _PHOTO_UNAVAILABLE_REPLY,
        }

        for outcome, expected_reply in expected.items():
            state = _build_state(_preview_data(seller, category, city))
            message = _build_message()

            with (
                patch(
                    "telegram_bot.handlers.ad_create.submit.translate_all_languages",
                    _mock_translate,
                ),
                patch(
                    "telegram_bot.handlers.ad_create.submit.submit_ad",
                    return_value=SubmitAdResult(outcome, []),
                ),
            ):
                await process_preview(message, state)

            rendered = str(message.answer.await_args.args[0])
            assert rendered == expected_reply, (
                f"{outcome.value!r} rendered the wrong message: {rendered!r}"
            )
            assert "was deleted" not in rendered, (
                f"{outcome.value!r} must not claim the draft was deleted"
            )

    @pytest.mark.asyncio
    async def test_photo_unavailable_repeated_confirms_do_not_loop(
        self, seller, category, city
    ) -> None:
        """Repeated confirms on ``PHOTO_UNAVAILABLE`` stay bounded.

        A stale photo list would make every re-confirm hit the missing-file
        branch again, creating and discarding a DRAFT forever. The fix clears
        ``photos`` and sends the seller to the photos step, so the second
        attempt reaches the photo branch (not another preview submission) and
        the fresh DRAFT is real.
        """
        from apps.ads.services.submission import (
            SubmitAdOutcome,
            SubmitAdResult,
        )
        from telegram_bot.handlers.ad_create import AdCreateForm, process_preview

        data = _preview_data(
            seller,
            category,
            city,
            photos=[
                {"storage_key": "staging/gone", "telegram_file_id": "f", "position": 0}
            ],
        )
        state = _build_state(data)
        message = _build_message()

        with (
            patch(
                "telegram_bot.handlers.ad_create.submit.translate_all_languages",
                _mock_translate,
            ),
            patch(
                "telegram_bot.handlers.ad_create.submit.submit_ad",
                return_value=SubmitAdResult(SubmitAdOutcome.PHOTO_UNAVAILABLE, []),
            ),
        ):
            await process_preview(message, state)
            first_update = state.update.await_args.args[0]
            first_ad_id = first_update["ad_id"]
            # The stale photo list is cleared and the FSM re-pointed at photos.
            assert first_update["photos"] == []
            state.set_state.assert_awaited_with(AdCreateForm.photos)

            # The cleared state is what the next attempt sees: no stale photo
            # keys, so a re-confirm cannot loop on the missing file.
            data_after_first = {**data, **first_update}
            state.get_data = AsyncMock(return_value=data_after_first)
            state.update.reset_mock()
            await process_preview(message, state)
            second_ad_id = state.update.await_args.args[0]["ad_id"]

        assert second_ad_id != first_ad_id, "a fresh draft must be created each time"

        from asgiref.sync import sync_to_async

        from apps.ads.models import Ad

        # Bounded: exactly one live DRAFT for the user (create_draft_ad replaces
        # the prior one), never an ever-growing tail from an unbounded loop.
        drafts = await sync_to_async(list)(
            Ad.objects.filter(user_id=seller.id, status=AdStatus.DRAFT)
        )
        assert len(drafts) == 1

    @pytest.mark.asyncio
    async def test_consent_required_clears_state_and_shows_its_own_message(
        self, seller, category, city
    ) -> None:
        """``CONSENT_REQUIRED`` is terminal for the dialog: answer + clear.

        Unlike the recoverable non-content outcomes, a consent refusal cannot
        be retried by pressing confirm again (the same gate would refuse), so
        the handler answers the outcome's own message and clears the FSM rather
        than re-pointing it at a fresh draft.
        """
        from apps.ads.services.submission import (
            SubmitAdOutcome,
            SubmitAdResult,
        )
        from telegram_bot.handlers.ad_create import process_preview

        state = _build_state(_preview_data(seller, category, city))
        message = _build_message()

        with (
            patch(
                "telegram_bot.handlers.ad_create.submit.translate_all_languages",
                _mock_translate,
            ),
            patch(
                "telegram_bot.handlers.ad_create.submit.submit_ad",
                return_value=SubmitAdResult(
                    SubmitAdOutcome.CONSENT_REQUIRED, ["consent needed"]
                ),
            ),
        ):
            await process_preview(message, state)

        assert message.answer.await_args.args[0] == "consent needed"
        state.clear.assert_awaited()
        state.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_moderation_failed_clears_state(
        self, seller, category, city
    ) -> None:
        """A genuine content failure still clears the state and blames content."""
        from apps.ads.services.submission import (
            SubmitAdOutcome,
            SubmitAdResult,
        )
        from telegram_bot.handlers.ad_create import process_preview

        state = _build_state(_preview_data(seller, category, city, ad_id=1))
        message = _build_message()

        with (
            patch(
                "telegram_bot.handlers.ad_create.submit.translate_all_languages",
                _mock_translate,
            ),
            patch(
                "telegram_bot.handlers.ad_create.submit.submit_ad",
                return_value=SubmitAdResult(
                    SubmitAdOutcome.MODERATION_FAILED, ["Banned word"]
                ),
            ),
        ):
            await process_preview(message, state)

        assert message.answer.await_args.args[0] == "Banned word"
        state.clear.assert_awaited()
        state.update.assert_not_awaited()


class TestDeprecatedExpiredStringIsNotReintroduced:
    """The catch-all expired-draft string must not be revived.

    It was replaced by three per-outcome messages. This guard keeps the
    catalogs from accumulating a *second* expired-draft msgid; the repo-wide
    ``test_i18n_completeness.py`` already guards ru/bs non-empty coverage, so
    the per-string translation check is deliberately not duplicated here.
    """

    def test_no_second_expired_string_exists(self) -> None:
        """At most one msgid mentions 'draft expired' across the catalogs.

        The deprecated string may still exist as a single orphaned catalog
        entry (``makemessages`` has not swept it yet); a second one would mean
        the old catch-all was reintroduced alongside the per-outcome messages.
        """
        from pathlib import Path

        from django.conf import settings

        locale_root = Path(settings.LOCALE_PATHS[0])
        for locale in ("ru", "bs", "en"):
            po_path = locale_root / locale / "LC_MESSAGES" / "django.po"
            text = po_path.read_text(encoding="utf-8")
            active_lines = [
                line
                for line in text.splitlines()
                if line.startswith("msgid ") and "draft expired" in line.lower()
            ]
            assert len(active_lines) <= 1, (
                f"expected at most one expired-draft msgid in {locale}, "
                f"found {len(active_lines)}"
            )

