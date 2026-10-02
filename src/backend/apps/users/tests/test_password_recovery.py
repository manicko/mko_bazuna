"""Execution tests for the documented credential-recovery procedure.

``docs/ops/docker-deployment.md`` documents ``manage.py changepassword`` as the
only supported way to change an admin password. These tests *run* that command
rather than pattern-matching the markdown, pinning the two properties the
procedure depends on:

* a policy-compliant value is accepted and the stored credential changes, and
* a value that violates ``AUTH_PASSWORD_VALIDATORS`` is refused and the stored
  credential is left byte-identical.

``changepassword`` prompts through ``getpass.getpass`` inside
``django.contrib.auth.management.commands.changepassword``. The command does
``import getpass``, so its module attribute *is* the stdlib module object — a
``setattr`` on it would mutate ``stdlib_getpass.getpass`` process-wide. These
tests instead rebind the module-local ``getpass`` name with a ``SimpleNamespace``
stub, so the substitution is confined to that one module.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from django.contrib.auth.hashers import check_password
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_USERNAME = "recovery-target"
_KNOWN_RAW_PASSWORD = "correct horse battery staple"
_NEW_RAW_PASSWORD = "s3cur3-Str0ng-Passphrase!"


@pytest.fixture
def staff_user() -> User:
    """A staff account with a usable, known credential."""
    user = User.objects.create(
        telegram_id=930000201,
        chat_id=930000201,
        username=_USERNAME,
        is_staff=True,
    )
    user.set_password(_KNOWN_RAW_PASSWORD)
    user.save()
    return user


@pytest.fixture
def _stub_getpass(monkeypatch: pytest.MonkeyPatch):
    """Replace the ``getpass`` name in the ``changepassword`` command module.

    Returns a callable that installs a fixed response sequence, so a test can
    drive the command's prompt loop without a terminal.
    """

    def install(responses: list[str]) -> None:
        import django.contrib.auth.management.commands.changepassword as module

        iterator: Iterator[str] = iter(responses)
        stub = SimpleNamespace(
            getpass=lambda *a, **k: next(iterator),
            getuser=lambda *a, **k: _USERNAME,
        )
        monkeypatch.setattr(module, "getpass", stub)

    return install


def test_documented_password_change_procedure_works(
    staff_user: User, _stub_getpass
) -> None:
    """``manage.py changepassword`` stores a new, policy-compliant credential."""
    assert staff_user.check_password(_KNOWN_RAW_PASSWORD) is True  # positive control
    hash_before = User.objects.get(pk=staff_user.pk).password

    # The command prompts twice (new value, then confirmation).
    _stub_getpass([_NEW_RAW_PASSWORD, _NEW_RAW_PASSWORD])
    call_command("changepassword", _USERNAME)

    staff_user.refresh_from_db()
    assert check_password(_NEW_RAW_PASSWORD, staff_user.password) is True
    assert staff_user.password != hash_before, "the stored hash must change"
    assert check_password(_KNOWN_RAW_PASSWORD, staff_user.password) is False


def test_documented_procedure_refuses_a_policy_violating_password(
    staff_user: User, _stub_getpass
) -> None:
    """A value failing ``AUTH_PASSWORD_VALIDATORS`` is refused, hash untouched."""
    assert staff_user.check_password(_KNOWN_RAW_PASSWORD) is True  # positive control
    hash_before = User.objects.get(pk=staff_user.pk).password

    # Well short of MinimumLengthValidator's 10-character floor. The command
    # retries up to MAX_TRIES=3 times (two prompts each) before aborting.
    violating = "short"
    _stub_getpass([violating] * 6)

    with pytest.raises(CommandError):
        call_command("changepassword", _USERNAME)

    staff_user.refresh_from_db()
    assert staff_user.password == hash_before, "the stored hash must be byte-identical"
