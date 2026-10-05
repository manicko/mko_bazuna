"""
Bound ``saved_searches.query`` with a real ``VARCHAR(200)`` column (08-SRCH-011).

``SavedSearch.query`` was an unbounded ``TextField`` with no ``max_length``, and
``save_search`` read ``request.POST`` directly (there is no DTO on this path).
A 50 000-character query round-tripped intact, and ``send_alerts.Command.
_collect_alerts`` iterates every ``SavedSearch(is_active=True)`` on an ungated
daily schedule, building one ``websearch_to_tsquery`` per row — so the bound
must hold for the bot, the admin and any management command, not only for the
POST handler.

``max_length=200`` becomes a **schema bound** (PostgreSQL ``VARCHAR(200)``),
matching the two existing reference points in this app — ``PopularSearch.query``
and ``SearchHistory.query``. It is deliberately NOT a ``MaxLengthValidator``,
which does not fire on ``save()`` and would leave the bot, the admin and a
management command unbounded.

The fail-loudly pre-check that counted rows longer than 200 characters used
``query__length__gt``, which Django raises at query time for a ``TextField``.
Because the ``AlterField`` below is a later operation, the pre-check ran against
the still-``TextField`` model state, so every ``migrate`` aborted with
``FieldError: Unsupported lookup 'length__gt' for TextField``. That broken step
has been **removed** from this migration (see ``0008`` for the replacement); it
left no schema trace, so removing it does not change the resulting state.
Truncating inside the migration was rejected: it would silently change what a
user's saved search matches, which is exactly the product risk this block exists
to prevent — applying a different rule inside the migration would be
incoherent. The fail-loudly pre-check is restored, against the now-``VARCHAR``
column, by ``0008_restore_saved_search_over_cap_check``.

The reverse is a plain ``AlterField`` reversal; this migration is not
irreversible (no row is moved or removed).
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("search", "0006_deduplicate_and_unique_popular_search"),
    ]

    operations = [
        migrations.AlterField(
            model_name="savedsearch",
            name="query",
            field=models.CharField(
                blank=True,
                max_length=200,
                null=True,
                help_text=(
                    "FTS query string stored in the user's language; matched against "
                    "the per-language search vector (no query-time translation). "
                    "Bounded at the model so the scheduler, bot, admin and management "
                    "commands cannot persist an unbounded value (08-SRCH-011)."
                ),
            ),
        ),
    ]
