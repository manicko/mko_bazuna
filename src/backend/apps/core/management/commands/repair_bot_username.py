"""
Repair an invalid SiteConfig.bot_username from the BOT_USERNAME setting.

Why this exists: migration 0003 seeded the singleton from settings.BOT_USERNAME
via QuerySet.update(), which bypasses full_clean(), so a deployment that shipped
the .env template value persisted "<your-bot-username>" into a field whose own
RegexValidator rejects it. The database is the source of truth after that
migration (get_bot_username() reads the model, not the setting), so correcting
.env.prod alone changes nothing on a deployed site.

What it does, and deliberately does not do:
  - It repairs the stored value ONLY when that value fails the model's validator.
    A valid value — including one an operator set through the Django admin — is
    never overwritten. The admin is the operator of record for this field.
  - It refuses (non-zero exit) when the setting it would copy from is itself
    empty or malformed, rather than substituting the model default. Doing the
    latter would manufacture the same silent dead link this command exists to
    repair.
  - It uses instance.save(), not QuerySet.update(). save() fires the post_save
    receiver in apps.core.signals, which invalidates both the site-config and the
    bot-username cache keys. update() emits no signal and the stale value would
    survive in the cache for SITE_CONFIG_CACHE_TTL (1 hour) — the most likely
    "the fix is broken" report this command will generate.
  - It is idempotent: a second run finds a valid value and does nothing.
  - It is safe to run concurrently: an advisory lock plus transaction.atomic().

Equivalent manual path: SiteConfig is registered in the Django admin and
bot_username is an editable, validated form field, so an operator who knows their
handle can simply edit the row. See docs/01-spec/contact-us.md.
"""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.enums import AdvisoryLockId
from apps.core.models import SiteConfig
from apps.core.utils.advisory_lock import advisory_lock
from config.settings.secret_validation import is_valid_bot_username

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Repair an invalid SiteConfig.bot_username from the BOT_USERNAME setting."""

    help = (
        "Re-sync SiteConfig.bot_username from BOT_USERNAME when the stored value "
        "fails the model validator; never overwrites a valid value"
    )

    def add_arguments(self, parser) -> None:
        """Add the dry-run flag."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Report what would change without writing anything",
        )

    def handle(self, *args, **options) -> None:
        """Repair the stored bot username when it fails the validator."""
        dry_run: bool = options["dry_run"]
        source: str = getattr(settings, "BOT_USERNAME", "") or ""

        if not is_valid_bot_username(source):
            # Case 1: the source is unusable. Refuse rather than substitute the
            # model default — that would reproduce the silent dead link.
            raise CommandError(
                "Cannot repair SiteConfig.bot_username: the BOT_USERNAME setting is "
                "missing, a template placeholder, or malformed. Set the real Telegram "
                "handle (no @ prefix) in the .env.prod runtime file, or edit the row "
                "in the Django admin, then re-run. The stored value was left unchanged."
            )

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            with advisory_lock(AdvisoryLockId.REPAIR_BOT_USERNAME):
                config = SiteConfig.get_singleton()

                if is_valid_bot_username(config.bot_username):
                    # Case 2: nothing to do. A correct admin-edited value wins.
                    logger.info(
                        "SiteConfig.bot_username is already valid; nothing to repair."
                    )
                    return

                logger.warning(
                    "SiteConfig.bot_username does not satisfy the model validator; "
                    "repairing it from the BOT_USERNAME setting."
                )
                if dry_run:
                    logger.info(
                        "DRY RUN: would repair SiteConfig.bot_username and "
                        "invalidate the bot-username cache"
                    )
                    return

                config.bot_username = source
                config.full_clean()
                config.save()  # fires post_save -> invalidates both cache keys
                logger.info(
                    "Repaired SiteConfig.bot_username from the BOT_USERNAME "
                    "setting; the bot-username cache was invalidated."
                )
