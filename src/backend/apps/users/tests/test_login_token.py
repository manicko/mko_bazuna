"""
Tests for the ``apps.users.services.login_token`` service module (ENT-005).

This is the deliverable of the ENT-005 extraction: the ``LoginToken``
lifecycle (issue / claim / consume) is owned by a services module and is
testable synchronously — without HTTP and without Telegram. The module's
contract is written here rather than into ``test_login.py`` so that the
eleven must-survive suites keep passing byte-identical and the refactor stays
auditable.

Honest limits (stated, not skipped):
- Every behavioural case below is green *before* the extraction when expressed
  against the pre-refactor code paths — that is the point of a refactor.
- No behavioural test can discriminate ``telegram_id=<observed>`` from
  ``telegram_id IS NOT NULL`` in the consume predicate: given the preceding
  read has already excluded the ``NULL`` case the two spellings are
  semantically equivalent by construction, and no production caller can supply
  a foreign id. ``TestClaimConsumeAgreement::test_d_never_claimed_is_pending``
  is the closest proxy (it fails if the *read* guard disappears). The identity
  binding's remaining protection is structural and documentary — see
  ``TestLoginHandshakeOwnership``.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from apps.users.models import LoginToken, User
from apps.users.services.login_token import (
    RETURNING_COLUMNS,
    _hash_browser_id,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# A 32-char URL-safe token matching the bot's deep-link pattern.
_LOGIN_PATTERN = re.compile(r"^login_([A-Za-z0-9_-]{32})$")
_URLSAFE_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
)

# The browser id every directly-built row in this module is bound to. Under
# G-1a's fail-closed policy a row with no binding is refused (UNBOUND), so the
# helper below must bind its rows to keep the existing consume cases meaningful.
# Exactly 22 URL-safe chars — the shape secrets.token_urlsafe(16) produces.
_BROWSER_ID = "testbrowserid0abcdefgh"

# A second, distinct well-formed browser id for cross-binding supersession tests.
_OTHER_BROWSER_ID = "otherbrowserid0abcdefg"


def _make_token(
    raw_token: str,
    *,
    telegram_id: int | None = None,
    consumed_at=None,
    expires_at=None,
) -> LoginToken:
    """Create a ``LoginToken`` row for a known raw token, bound to a browser."""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    if expires_at is None:
        expires_at = timezone.now() + timedelta(hours=1)
    return LoginToken.objects.create(
        token_hash=token_hash,
        telegram_id=telegram_id,
        consumed_at=consumed_at,
        expires_at=expires_at,
        browser_binding=_hash_browser_id(_BROWSER_ID),
    )


def _claim(token_hash: str, telegram_id: int, now=None) -> LoginToken | None:
    """Synchronous wrapper over the service claim for readable tests."""
    from apps.users.services.login_token import claim_token

    if now is None:
        now = timezone.now()
    return claim_token(token_hash, telegram_id, now)


# ---------------------------------------------------------------------------
# TestIssueToken
# ---------------------------------------------------------------------------


class TestIssueToken:
    """``issue_token`` mints a fresh token, persisting only the SHA-256 hash."""

    def test_stores_sha256_of_raw(self) -> None:
        from apps.users.services.login_token import issue_token

        issued = issue_token()
        stored = LoginToken.objects.get(token_hash=issued.token_hash)
        expected = hashlib.sha256(issued.raw_token.encode()).hexdigest()
        assert stored.token_hash == expected

    def test_leaves_telegram_id_and_consumed_at_null(self) -> None:
        from apps.users.services.login_token import issue_token

        issued = issue_token()
        stored = LoginToken.objects.get(token_hash=issued.token_hash)
        assert stored.telegram_id is None
        assert stored.consumed_at is None

    def test_expires_in_5_minutes(self) -> None:
        from apps.users.services.login_token import issue_token

        issued = issue_token()
        stored = LoginToken.objects.get(token_hash=issued.token_hash)
        remaining = stored.expires_at - timezone.now()
        assert 240 <= remaining.total_seconds() <= 300

    def test_raw_never_persisted(self) -> None:
        from apps.users.services.login_token import issue_token

        issued = issue_token()
        assert len(issued.raw_token) == 32
        assert len(issued.token_hash) == 64
        # The stored value is the hash, never the raw token.
        stored = LoginToken.objects.get(token_hash=issued.token_hash)
        assert stored.token_hash != issued.raw_token

    def test_raw_token_is_urlsafe_and_matches_pattern(self) -> None:
        from apps.users.services.login_token import issue_token

        issued = issue_token()
        assert all(c in _URLSAFE_CHARS for c in issued.raw_token)
        # The raw token is exactly the `{32}` captured group of the bot's
        # deep-link pattern: /start login_<32-char-token>.
        assert re.fullmatch(r"[A-Za-z0-9_-]{32}", issued.raw_token) is not None
        assert _LOGIN_PATTERN.match(f"login_{issued.raw_token}") is not None

    def test_two_issues_differ(self) -> None:
        from apps.users.services.login_token import issue_token

        first = issue_token()
        second = issue_token()
        assert first.raw_token != second.raw_token
        assert first.token_hash != second.token_hash


# ---------------------------------------------------------------------------
# TestIssueTokenSupersession
# ---------------------------------------------------------------------------


class TestIssueTokenSupersession:
    """``issue_token`` supersedes a browser's earlier live *unclaimed* token.

    All assertions go through ``claim_token`` / ``consume_token`` — never a raw
    SQL row count — so the tests measure redeemability, not table shape.
    """

    def test_second_issue_supersedes_the_first(self) -> None:
        """The first token is neither claimable nor redeemable after a re-issue."""
        from apps.users.services.login_token import (
            ConsumeOutcome,
            claim_token,
            consume_token,
            issue_token,
        )

        first = issue_token(browser_id=_BROWSER_ID)
        second = issue_token(browser_id=_BROWSER_ID)

        # The first is superseded: the bot cannot claim it ...
        assert claim_token(first.token_hash, 700000100, timezone.now()) is None
        # ... and the web cannot redeem it (it reads GONE, not PENDING).
        gone = consume_token(first.raw_token, browser_id=_BROWSER_ID)
        assert gone.outcome is ConsumeOutcome.GONE

        # The second is live: claimable ...
        assert claim_token(second.token_hash, 700000100, timezone.now()) is not None
        # ... and redeemable end to end by the issuing browser.
        consumed = consume_token(second.raw_token, browser_id=_BROWSER_ID)
        assert consumed.outcome is ConsumeOutcome.CONSUMED
        assert consumed.telegram_id == 700000100

    def test_second_token_stays_claimable_and_consumable(self) -> None:
        """The token created *after* the UPDATE must survive it.

        Its distinctive failure mode is ``the freshly created token is already
        dead``: a later ``UPDATE`` can only burn rows that already existed, so
        the just-created row would itself be superseded and read ``GONE``
        rather than ``CONSUMED``. Reversing the order fails several of the new
        tests, so this is not the only order-sensitive test — it is the one
        that isolates *that* consequence (the surviving token being burned by
        the issue that minted it), which the others do not.
        """
        from apps.users.services.login_token import (
            ConsumeOutcome,
            claim_token,
            consume_token,
            issue_token,
        )

        issue_token(browser_id=_BROWSER_ID)
        second = issue_token(browser_id=_BROWSER_ID)

        assert claim_token(second.token_hash, 700000101, timezone.now()) is not None
        result = consume_token(second.raw_token, browser_id=_BROWSER_ID)
        assert result.outcome is ConsumeOutcome.CONSUMED
        assert result.telegram_id == 700000101

    def test_issue_does_not_supersede_another_browser(self) -> None:
        """One browser's issue never reaches another browser's live token."""
        from apps.users.services.login_token import (
            ConsumeOutcome,
            claim_token,
            consume_token,
            issue_token,
        )

        other = issue_token(browser_id=_OTHER_BROWSER_ID)
        issue_token(browser_id=_BROWSER_ID)  # a different profile issues

        # The other browser's token is untouched: still claimable ...
        assert claim_token(other.token_hash, 700000102, timezone.now()) is not None
        # ... and still redeemable by its own browser.
        result = consume_token(other.raw_token, browser_id=_OTHER_BROWSER_ID)
        assert result.outcome is ConsumeOutcome.CONSUMED
        assert result.telegram_id == 700000102

    def test_supersession_does_not_touch_a_claimed_token(self) -> None:
        """A token the bot already claimed is mid-handshake and must not burn.

        ``telegram_id IS NULL`` is the load-bearing conjunct: without it a
        same-site prefetch of ``/login/issue/`` would kill a login whose user
        already tapped the Telegram button.
        """
        from apps.users.services.login_token import (
            ConsumeOutcome,
            claim_token,
            consume_token,
            issue_token,
        )

        first = issue_token(browser_id=_BROWSER_ID)
        assert claim_token(first.token_hash, 700000103, timezone.now()) is not None

        # A second issue from the same browser must leave the claimed token
        # alone ...
        second = issue_token(browser_id=_BROWSER_ID)
        assert second.token_hash != first.token_hash

        # ... so it is still redeemable end to end.
        result = consume_token(first.raw_token, browser_id=_BROWSER_ID)
        assert result.outcome is ConsumeOutcome.CONSUMED
        assert result.telegram_id == 700000103

    def test_supersession_leaves_a_live_null_binding_row_claimable(self) -> None:
        """An *unclaimed* ``NULL``-binding row survives an issue.

        This is the assertion that pins ``G-4g`` and genuinely discriminates a
        forbidden ``OR browser_binding IS NULL`` disjunct: such a disjunct would
        burn this row, so the post-issue ``claim_token`` would return ``None``.

        The observation is deliberately ``claim_token(...) is not None`` after
        the issue, *not* ``consume_token``: an unclaimed ``NULL`` row reads
        ``PENDING`` (the binding gate sits after the ``PENDING`` check), so it
        never reaches ``UNBOUND`` and cannot be asserted through
        ``consume_token``. Claiming the row first would make the ``UNBOUND``
        assertion possible but destroy the discriminating power, because
        ``telegram_id__isnull=True`` shields a claimed row from any
        ``browser_binding`` disjunct.
        """
        from apps.users.services.login_token import claim_token, issue_token

        raw = "o" * 32
        unbound = _make_token(raw)
        LoginToken.objects.filter(pk=unbound.pk).update(browser_binding=None)

        issue_token(browser_id=_BROWSER_ID)

        # The live NULL-binding row was not burned: the bot can still claim it.
        assert claim_token(unbound.token_hash, 700000104, timezone.now()) is not None

    def test_supersession_does_not_burn_a_claimed_null_binding_row(self) -> None:
        """A *claimed* ``NULL``-binding row is not burned by an issue.

        Supersession is scoped to the issuing browser only; a legacy/unbound
        row is already unredeemable (``UNBOUND``) and must be left as-is. This
        row is claimed first so ``consume_token`` reaches the binding gate (an
        unclaimed row would read ``PENDING`` before the gate is consulted).
        """
        from apps.users.services.login_token import (
            ConsumeOutcome,
            claim_token,
            consume_token,
            issue_token,
        )

        raw = "o" * 32
        unbound = _make_token(raw)
        LoginToken.objects.filter(pk=unbound.pk).update(browser_binding=None)
        # Claim it so ``consume_token`` reaches the binding gate (an unclaimed
        # row would read PENDING before the gate is consulted).
        assert claim_token(unbound.token_hash, 700000104, timezone.now()) is not None

        issue_token(browser_id=_BROWSER_ID)

        # The NULL-binding row is not superseded: it reads UNBOUND, and its
        # consumed_at is still NULL — the burn never touched it.
        result = consume_token(raw, browser_id=_BROWSER_ID)
        assert result.outcome is ConsumeOutcome.UNBOUND
        unbound.refresh_from_db()
        assert unbound.consumed_at is None

    def test_supersession_log_leaks_no_raw_identifiers(self, caplog) -> None:
        """The supersession ``logger.info`` line carries no raw identifiers.

        The line ships to production (``prod.py`` sets the ``apps`` logger to
        ``INFO``) but emits nothing under test (``test.py`` defines no
        ``LOGGING`` dict, so the root logger is ``WARNING``). Forcing the
        service logger's level makes that production-visible line observable on
        an unauthenticated, rate-limit-only endpoint. It is placed here, not in
        ``test_consent.py::TestLoginStatusNoPii``: the emitter is
        ``apps.users.services.login_token``'s ``issue_token``, not the view, so
        coupling the assertion to a ``login_status`` HTTP round trip would
        misattribute the guard.
        """
        from apps.users.services.login_token import issue_token

        known_telegram_id = 700000105
        # A claimed row on this binding: it exists (and carries a raw
        # ``telegram_id``) but must never be superseded or named in the line.
        claimed = _make_token("p" * 32, telegram_id=known_telegram_id)
        assert claimed.telegram_id == known_telegram_id

        # One live unclaimed row for this binding, so the issue supersedes one.
        live = issue_token(browser_id=_BROWSER_ID)

        with caplog.at_level(
            logging.INFO, logger="apps.users.services.login_token"
        ):
            superseding = issue_token(browser_id=_BROWSER_ID)

        # The line is emitted and reports exactly the one superseded row.
        assert "superseded 1 prior unclaimed token(s)" in caplog.text
        # Neither raw token, nor the raw browser id, nor any telegram_id leaks.
        assert live.raw_token not in caplog.text
        assert superseding.raw_token not in caplog.text
        assert _BROWSER_ID not in caplog.text
        assert str(known_telegram_id) not in caplog.text


# ---------------------------------------------------------------------------
# TestClaimToken
# ---------------------------------------------------------------------------


class TestClaimToken:
    """``claim_token`` sets ``telegram_id`` on a live, unclaimed token."""

    def test_fresh_live_token_claimed_consumed_at_still_none(self) -> None:
        raw = "a" * 32
        token = _make_token(raw)
        claimed = _claim(token.token_hash, 700000001)
        assert claimed is not None
        assert claimed.telegram_id == 700000001
        # The web phase consumes it later — the claim must not set consumed_at.
        assert claimed.consumed_at is None

    def test_expired_token_not_claimable(self) -> None:
        raw = "b" * 32
        token = _make_token(raw, expires_at=timezone.now() - timedelta(hours=1))
        assert _claim(token.token_hash, 700000002) is None

    def test_already_consumed_token_not_claimable(self) -> None:
        raw = "c" * 32
        token = _make_token(
            raw, telegram_id=700000003, consumed_at=timezone.now()
        )
        assert _claim(token.token_hash, 700000004) is None

    def test_unknown_hash_not_claimable(self) -> None:
        assert _claim("f" * 64, 700000005) is None

    def test_second_claim_returns_none(self) -> None:
        raw = "d" * 32
        token = _make_token(raw)
        assert _claim(token.token_hash, 700000006) is not None
        # A different user cannot re-claim an already-claimed token.
        assert _claim(token.token_hash, 700000007) is None

    def test_claim_token_returning_matches_model_fields(self) -> None:
        """``RETURNING_COLUMNS`` and the claim SQL must cover every model field.

        Three discriminating assertions, because a stale ``RETURNING`` fails
        *silently* (``Model.__init__`` defaults a missing field to ``None``);
        a behavioural "no exception" check would prove nothing.
        """
        model_attnames = [f.attname for f in LoginToken._meta.concrete_fields]

        # (a) SECURITY: a model column absent from RETURNING would be silently
        # dropped to its default on every bot claim.
        assert set(RETURNING_COLUMNS) == set(model_attnames), (
            "RETURNING_COLUMNS must cover every LoginToken field; a missing "
            "column is silently defaulted (not an error) by Model.__init__."
        )

        # (b) CONSISTENCY (not security): declaration order drives the
        # concrete_fields order; divergence is fixed by reordering, which is free.
        assert tuple(RETURNING_COLUMNS) == tuple(model_attnames), (
            "RETURNING_COLUMNS order is a consistency obligation with "
            "LoginToken's declaration order, not a security one."
        )

        # (c) ROUND TRIP: a real claim returns an instance whose binding is
        # actually populated (catches a behavioural loss the set check misses).
        from apps.users.services.login_token import claim_token, issue_token

        issued = issue_token(browser_id=_BROWSER_ID)
        claimed = claim_token(issued.token_hash, 700000008, timezone.now())
        assert claimed is not None
        assert claimed.browser_binding is not None
        stored = LoginToken.objects.get(token_hash=issued.token_hash)
        assert claimed.browser_binding == stored.browser_binding


# ---------------------------------------------------------------------------
# TestConsumeToken
# ---------------------------------------------------------------------------


class TestConsumeToken:
    """``consume_token`` returns a typed ``ConsumeResult`` for every case."""

    def test_unknown_token_not_found(self) -> None:
        from apps.users.services.login_token import ConsumeOutcome, consume_token

        result = consume_token("z" * 32, browser_id=_BROWSER_ID)
        assert result.outcome is ConsumeOutcome.NOT_FOUND
        assert result.telegram_id is None

    def test_expired_token_gone(self) -> None:
        from apps.users.services.login_token import ConsumeOutcome, consume_token

        raw = "e" * 32
        _make_token(raw, expires_at=timezone.now() - timedelta(hours=1))
        result = consume_token(raw, browser_id=_BROWSER_ID)
        assert result.outcome is ConsumeOutcome.GONE

    def test_consumed_token_gone(self) -> None:
        from apps.users.services.login_token import ConsumeOutcome, consume_token

        raw = "g" * 32
        _make_token(raw, telegram_id=700000010, consumed_at=timezone.now())
        result = consume_token(raw, browser_id=_BROWSER_ID)
        assert result.outcome is ConsumeOutcome.GONE

    def test_unclaimed_live_token_pending(self) -> None:
        from apps.users.services.login_token import ConsumeOutcome, consume_token

        raw = "h" * 32
        token = _make_token(raw)
        result = consume_token(raw, browser_id=_BROWSER_ID)
        assert result.outcome is ConsumeOutcome.PENDING
        assert result.telegram_id is None
        # The read must not mutate the row — consumed_at stays NULL.
        token.refresh_from_db()
        assert token.consumed_at is None

    def test_claimed_token_consumed(self) -> None:
        from apps.users.services.login_token import ConsumeOutcome, consume_token

        raw = "i" * 32
        _make_token(raw, telegram_id=700000011)
        result = consume_token(raw, browser_id=_BROWSER_ID)
        assert result.outcome is ConsumeOutcome.CONSUMED
        assert result.telegram_id == 700000011
        # The UPDATE actually stamped consumed_at.
        token = LoginToken.objects.get(token_hash=hashlib.sha256(raw.encode()).hexdigest())
        assert token.consumed_at is not None

    def test_row_deleted_before_consume_not_found(self) -> None:
        from apps.users.services.login_token import ConsumeOutcome, consume_token

        raw = "j" * 32
        token = _make_token(raw)
        token.delete()
        result = consume_token(raw, browser_id=_BROWSER_ID)
        assert result.outcome is ConsumeOutcome.NOT_FOUND


# ---------------------------------------------------------------------------
# TestClaimConsumeAgreement
# ---------------------------------------------------------------------------


class TestClaimConsumeAgreement:
    """The claim and consume predicates agree on the (deliberately different)
    phase boundaries — the cross-predicate guard the report asks for."""

    def test_a_second_claim_does_not_rewrite_telegram_id(self) -> None:
        raw = "k" * 32
        token = _make_token(raw)
        assert _claim(token.token_hash, 700000020) is not None
        # Second claim by a different user is rejected ...
        assert _claim(token.token_hash, 700000021) is None
        # ... and the row's telegram_id is still the first claimer's.
        token.refresh_from_db()
        assert token.telegram_id == 700000020

    def test_b_consumed_token_not_claimable_by_anyone(self) -> None:
        from apps.users.services.login_token import consume_token

        raw = "l" * 32
        token = _make_token(raw, telegram_id=700000022)
        assert consume_token(raw, browser_id=_BROWSER_ID).outcome.value == "consumed"
        # Other direction of phase separation: after CONSUMED, no X can claim.
        for x in (700000023, 700000024):
            assert _claim(token.token_hash, x) is None

    def test_c_consumed_binds_to_the_claiming_user(self) -> None:
        from apps.users.services.login_token import ConsumeOutcome, consume_token

        # Users for BOTH the claiming and the non-claiming telegram_id exist.
        User.objects.create(
            telegram_id=700000030, chat_id=700000030, username="claimer"
        )
        User.objects.create(
            telegram_id=700000031, chat_id=700000031, username="other"
        )
        raw = "m" * 32
        token = _make_token(raw)
        assert _claim(token.token_hash, 700000030) is not None
        result = consume_token(raw, browser_id=_BROWSER_ID)
        assert result.outcome is ConsumeOutcome.CONSUMED
        assert result.telegram_id == 700000030
        token.refresh_from_db()
        assert token.consumed_at is not None

    def test_d_never_claimed_is_pending(self) -> None:
        from apps.users.services.login_token import ConsumeOutcome, consume_token

        raw = "n" * 32
        token = _make_token(raw)
        result = consume_token(raw, browser_id=_BROWSER_ID)
        # The case with real discriminating power: if the read's
        # ``telegram_id is None`` guard were deleted, the same input falls
        # through to the UPDATE, matches zero rows, and returns LOST_RACE
        # (410) instead of PENDING (204) — a silent failure of the two-phase
        # handshake.
        assert result.outcome is ConsumeOutcome.PENDING
        assert result.telegram_id is None
        token.refresh_from_db()
        assert token.consumed_at is None


# ---------------------------------------------------------------------------
# TestBindingDoesNotReachTheBot
# ---------------------------------------------------------------------------


class TestBindingDoesNotReachTheBot:
    """The bot is never handed a binding — proven at the source level.

    A signature-introspection test would require importing aiogram into the
    backend suite (or editing a bot test file), and ``src/telegram_bot/`` must
    stay byte-unchanged. Reading the handler as text is the same technique
    ``TestLoginHandshakeOwnership::test_bot_handler_has_no_raw_sql`` uses.
    """

    def test_bot_claim_is_not_given_a_binding(self) -> None:
        source = (
            Path(__file__).parents[4].joinpath("telegram_bot", "handlers", "login.py")
        ).read_text()

        assert "claim_token(token_hash, telegram_id, now)" in source
        assert "browser" not in source


# ---------------------------------------------------------------------------
# TestLoginHandshakeOwnership
# ---------------------------------------------------------------------------


class TestLoginHandshakeOwnership:
    """Structural assertions that the lifecycle is owned by one service module.

    This is the one genuinely red→green class: all three assertions are false
    before the extraction and true after. A green ownership test is not
    evidence of correctness — it is a structural tripwire so a future
    implementor knows where to move SQL rather than that the test is obsolete.
    """

    _OWNER = "apps.users.services.login_token"

    def test_three_operations_importable_from_one_module(self) -> None:
        # Must resolve from a single module by full path.
        from apps.users.services.login_token import (
            claim_token,
            consume_token,
            issue_token,
        )

        assert callable(issue_token)
        assert callable(claim_token)
        assert callable(consume_token)

    def test_consent_view_has_no_token_logic(self) -> None:
        source = Path(__file__).parents[1].joinpath("views", "consent.py").read_text()
        for forbidden in (
            "hashlib",
            "secrets",
            "LoginToken",
            "UPDATE login_tokens",
            ".update(consumed_at=",
        ):
            assert forbidden not in source, (
                f"consent.py must not contain {forbidden!r}; the consume/issue "
                f"predicates belong in {self._OWNER}"
            )

    def test_bot_handler_has_no_raw_sql(self) -> None:
        source = (
            Path(__file__).parents[4].joinpath("telegram_bot", "handlers", "login.py")
        ).read_text()
        # ``cursor.execute`` + ``UPDATE login_tokens`` together uniquely identify
        # raw SQL in the handler; ``RETURNING`` is deliberately not asserted
        # because the mandated thin-wrapper docstring mentions it in prose.
        for forbidden in (
            "UPDATE login_tokens",
            "cursor.execute",
        ):
            assert forbidden not in source, (
                f"handlers/login.py must not contain {forbidden!r}; the claim SQL "
                f"belongs in {self._OWNER}.claim_token"
            )
