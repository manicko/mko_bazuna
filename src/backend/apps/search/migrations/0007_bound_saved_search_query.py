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

The forward step runs a fail-loudly pre-check: it counts rows whose query is
longer than 200 characters and **raises** if any exist, so a deployment holding
dirty data refuses to migrate with an actionable message instead of failing with
an opaque ``value too long`` database error. Truncating inside the migration was
rejected: it would silently change what a user's saved search matches, which is
exactly the product risk this block exists to prevent — applying a different
rule inside the migration would be incoherent. The count is logged at INFO
either way.

The reverse is a plain ``AlterField`` reversal; this migration is not
irreversible (no row is moved or removed).
"""

import logging

from django.db import migrations, models

logger = logging.getLogger(__name__)

# The new column bound; also the threshold the pre-check counts against.
_QUERY_MAX_LENGTH = 200


def _refuse_over_cap_rows(apps, schema_editor):
    """Refuse to narrow the column while any stored query exceeds the bound.

    Raises:
        RuntimeError: If at least one ``SavedSearch.query`` is longer than
            ``_QUERY_MAX_LENGTH``. The message names the count so the operator
            can act (blank/trim the offending rows) before retrying.
    """
    SavedSearch = apps.get_model("search", "SavedSearch")
    over_cap = SavedSearch.objects.filter(query__length__gt=_QUERY_MAX_LENGTH).count()

    logger.info(
        "saved_searches.query rows over %s characters: %s (08-SRCH-011)",
        _QUERY_MAX_LENGTH,
        over_cap,
    )

    if over_cap:
        raise RuntimeError(
            f"Cannot bound saved_searches.query to {_QUERY_MAX_LENGTH} characters: "
            f"{over_cap} row(s) exceed the cap. Truncating would silently change "
            "what a saved search matches, so this migration refuses to proceed. "
            "Shorten or clear the offending rows, then re-run the migration."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("search", "0006_deduplicate_and_unique_popular_search"),
    ]

    operations = [
        migrations.RunPython(
            _refuse_over_cap_rows,
            reverse_code=migrations.RunPython.noop,
        ),
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
