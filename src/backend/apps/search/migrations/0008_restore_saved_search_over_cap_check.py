"""
Re-run the ``saved_searches.query`` over-cap guard with a supported lookup.

``0007_bound_saved_search_query`` leads with a ``RunPython`` pre-check that
counts rows whose query exceeds 200 characters. That step used
``query__length__gt``, which Django raises at query time for a ``TextField``:

    FieldError: Unsupported lookup 'length__gt' for TextField or join on the
    field not permitted.

At that point in ``0007`` the ``AlterField`` that narrows the column to
``VARCHAR(200)`` is a *later* operation, so the pre-check runs against the
still-``TextField`` model state — the lookup is unsupported exactly where it is
used. Because a ``RunPython`` step runs at ``migrate`` time, the failure is not
confined to a test: every fresh ``migrate`` (a deployment) aborts with the
``FieldError`` above. The data step is therefore a real deployment blocker.

:mod:`0007` is left intact on disk but with the broken step removed, so a fresh
database still narrows the column at the recorded ``0007`` boundary while an
already-migrated database (0007 applied) is untouched — its recorded migration
history does not change. This migration restores the fail-loudly guard *after*
0007's ``AlterField``, where ``query`` is ``VARCHAR(200)`` and
``Length("query")`` is valid SQL.

The guard's purpose is unchanged and still required: refuse to proceed when any
stored query already exceeds the bound, rather than truncating (which would
silently change what a saved search matches). On a fresh database this step sees
no rows and logs a count of zero; on a database that already applied 0007 the
same step is the actual enforcement point (the removed 0007 step never ran to
completion there). If either finds over-cap rows, the count is logged at INFO
and a ``RuntimeError`` names the count so the operator can act.
"""

import logging

from django.db import migrations
from django.db.models.functions import Length

logger = logging.getLogger(__name__)

# The new column bound; also the threshold the pre-check counts against.
_QUERY_MAX_LENGTH = 200


def _refuse_over_cap_rows(apps, schema_editor):
    """Refuse to keep the column under its bound while any query exceeds it.

    Raises:
        RuntimeError: If at least one ``SavedSearch.query`` is longer than
            ``_QUERY_MAX_LENGTH``. The message names the count so the operator
            can act (shorten or clear the offending rows) before retrying.
    """
    SavedSearch = apps.get_model("search", "SavedSearch")
    over_cap = (
        SavedSearch.objects.annotate(query_length=Length("query"))
        .filter(query_length__gt=_QUERY_MAX_LENGTH)
        .count()
    )

    logger.info(
        "saved_searches.query rows over %s characters: %s (08-SRCH-011)",
        _QUERY_MAX_LENGTH,
        over_cap,
    )

    if over_cap:
        raise RuntimeError(
            f"Cannot hold saved_searches.query to {_QUERY_MAX_LENGTH} characters: "
            f"{over_cap} row(s) exceed the cap. Truncating would silently change "
            "what a saved search matches, so this migration refuses to proceed. "
            "Shorten or clear the offending rows, then re-run the migration."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("search", "0007_bound_saved_search_query"),
    ]

    operations = [
        migrations.RunPython(
            _refuse_over_cap_rows,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
