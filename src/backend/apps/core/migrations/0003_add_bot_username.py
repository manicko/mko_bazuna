"""
Add bot_username field to SiteConfig and seed from settings.BOT_USERNAME.

Part of Block A (contact-us): migrates the bot username from the
``settings.BOT_USERNAME`` env var into the ``SiteConfig`` singleton
so it is editable in Django admin.

Editing this applied migration protects **fresh databases only**: an
already-migrated deployment does not re-run it, and even a forced re-run is inert
in the two cases that matter. If the singleton row does not exist the
``filter(pk=1, bot_username="bazuna_bot")`` guard matches nothing; and a row that
already holds a placeholder is not matched either, because its value is no longer
the factory default. Repairing an already-seeded deployment is therefore **not**
this migration's job — it is ``manage.py repair_bot_username`` (or a Django-admin
edit of the singleton).

The write goes through ``save()`` rather than ``QuerySet.update()``, which fires
``post_save`` and invalidates the cached bot username. That is correct here even
though ``reverse_code`` is ``noop``: a migration-time cache invalidation is
harmless and, for a one-shot bootstrap, useful.

A ``settings.BOT_USERNAME`` that is empty **or fails the field's own validator**
resolves to the field default (``bazuna_bot``) rather than being written or
raised on. This closes the validator bypass without turning a malformed
operational env value into an aborted ``migrate`` run; correcting an
already-seeded row is ``manage.py repair_bot_username``'s job.
"""

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import migrations, models

# The validator regex as declared on the field below. Kept inline so this
# historical migration stays frozen: it must not import live application code
# whose pattern could later drift from the one this migration actually applied.
_BOT_USERNAME_RE = RegexValidator(
    message="Bot username must be 3-32 characters, alphanumeric and underscore only",
    regex="^[A-Za-z0-9_]{3,32}$",
)


def seed_bot_username(apps, schema_editor):
    """Seed SiteConfig.bot_username from settings, validating before writing.

    ``schema_editor`` is accepted for the RunPython contract and never used.
    """
    SiteConfig = apps.get_model("core", "SiteConfig")

    # Read BOT_USERNAME from settings; fall back to the field default when the
    # setting is empty OR fails the field's own validator. An unusable setting
    # value is treated exactly like an empty one: the seed never writes a value
    # the RegexValidator rejects, and it never aborts the migration run over an
    # operational env value it cannot control. Repairing an already-seeded
    # deployment is manage.py repair_bot_username's job, not this migration's.
    from django.conf import settings as dj_settings

    configured = getattr(dj_settings, "BOT_USERNAME", "") or ""
    fallback = SiteConfig._meta.get_field("bot_username").default
    try:
        _BOT_USERNAME_RE(configured)
        bot_username = configured
    except ValidationError:
        bot_username = fallback
    # Only seed rows that are still at the factory default — never
    # overwrite an admin-edited value on re-run (migration-workflow.md:285).
    config = SiteConfig.objects.filter(pk=1, bot_username=fallback).first()
    if config is None:
        return
    config.bot_username = bot_username
    # update() bypasses full_clean(), which is how a template value
    # (BOT_USERNAME=<your-bot-username>) was being persisted into a field whose
    # own RegexValidator rejects it. save() rather than update() also fires
    # post_save, so the bot-username cache is invalidated — correct here even
    # though reverse_code is a noop.
    config.full_clean()
    config.save()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_seed_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="bot_username",
            field=models.CharField(
                default="bazuna_bot",
                help_text="Telegram bot username without @ prefix",
                max_length=32,
                validators=[
                    RegexValidator(
                        message="Bot username must be 3-32 characters, alphanumeric and underscore only",
                        regex="^[A-Za-z0-9_]{3,32}$",
                    ),
                ],
            ),
        ),
        migrations.RunPython(
            seed_bot_username,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
