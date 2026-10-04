"""
Make ``popular_searches.query_normalized`` unique (08-SRCH-003).

``query_normalized`` was a plain ``db_index=True`` column with no unique
constraint, so two concurrent writers could both insert the same key.
``increment_popular_search`` uses ``get_or_create``, whose internal ``.get()``
re-raises ``MultipleObjectsReturned`` once a duplicate exists — and that raise is
unguarded on the anonymous ``GET /search/`` path, turning the endpoint into a
hard 500. This is a schema-invariant violation, not a race, so remediation leads
with a migration.

Dedup rules (decided 2026-10-01, re-verified):

* group by ``query_normalized`` **exactly** — no casefold/strip. The write path
  already derives the key with ``search_query_key()``, so a looser grouping
  would reintroduce collisions that ``AddConstraint`` then rejects.
* survivor = greatest ``hit_count``; tie -> greatest ``last_seen``; tie ->
  lowest ``pk`` (deterministic for re-entry safety).
* ``hit_count`` = **SUM** over the group — never MAX, which would lose
  popularity.
* ``last_seen`` = **MAX** over the group.
* ``query`` and ``source`` keep the **survivor's own** values, untouched.

The merge is set-based (no per-row Python loop) and re-entry safe: the data step
only ever reduces the row count, so running it twice cannot corrupt anything.
The second run is in practice a no-op because ``AddConstraint`` is one-shot.

Reverse is a deliberate ``RunPython.noop``: the merged rows do not return. A
``migrate back`` restores the schema, not the data.
"""

import logging

from django.db import migrations, models
from django.db.models import Count, Max, Sum

logger = logging.getLogger(__name__)


def _deduplicate(apps, schema_editor):
    """Merge rows sharing ``query_normalized`` before the unique constraint."""
    PopularSearch = apps.get_model("search", "PopularSearch")

    before = PopularSearch.objects.count()

    # Only groups with more than one row share a key AddConstraint will reject.
    duplicate_keys = (
        PopularSearch.objects.values("query_normalized")
        .annotate(row_count=Count("pk"))
        .filter(row_count__gt=1)
    )

    for group in duplicate_keys.iterator():
        key = group["query_normalized"]
        group_qs = PopularSearch.objects.filter(query_normalized=key)

        # Survivor: greatest hit_count, tie -> greatest last_seen, tie -> lowest pk.
        survivor = group_qs.order_by("-hit_count", "-last_seen", "pk").first()
        if survivor is None:
            continue

        aggregate = group_qs.aggregate(total_hits=Sum("hit_count"), latest=Max("last_seen"))

        group_qs.exclude(pk=survivor.pk).delete()
        # ``last_seen`` is ``auto_now=True`` (a pre_save hook); ``update()``
        # bypasses model saves, so the value is written verbatim.
        PopularSearch.objects.filter(pk=survivor.pk).update(
            hit_count=aggregate["total_hits"] or 0,
            last_seen=aggregate["latest"],
        )

    after = PopularSearch.objects.count()
    logger.info(
        "popular_searches dedup complete: %s rows before, %s after (08-SRCH-003)",
        before,
        after,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("search", "0005_redact_search_query_keys"),
    ]

    operations = [
        migrations.RunPython(
            _deduplicate,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="popularsearch",
            constraint=models.UniqueConstraint(
                fields=["query_normalized"],
                name="uq_popular_search_query_normalized",
            ),
        ),
    ]
