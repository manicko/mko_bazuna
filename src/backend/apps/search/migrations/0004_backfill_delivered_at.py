"""
Data migration: backfill ``SavedSearchNotification.delivered_at`` (03-DB-007).

A pre-existing row was, under the previous contract, treated as a delivery
receipt: it suppressed the pair from both delivery paths. The delivery-state
contract makes that decision depend on ``delivered_at IS NOT NULL`` instead, so
a nullable column with no backfill would make every pre-existing row eligible
again — and the next live, ungated 08:00 UTC ``send_alerts`` run would
re-notify every previously notified pair to every subscribed buyer.

The backfill is therefore BEHAVIOUR-PRESERVING: every row that exists at
migration time is marked delivered at its own ``sent_at``. ``sent_at`` is
``auto_now_add``, so ``F("sent_at")`` is a set-based ``UPDATE`` — no row loop,
no per-row Python, safe at any table size.

Reverse is a NO-OP, deliberately: a reverse that NULLs ``delivered_at`` would
re-arm exactly the mass re-notification this backfill prevents, so it must not.
"""

from django.db import migrations
from django.db.models import F


def backfill_delivered_at(apps, schema_editor):
    """Mark every pre-existing attempt record as delivered at its ``sent_at``."""
    SavedSearchNotification = apps.get_model("search", "SavedSearchNotification")
    SavedSearchNotification.objects.filter(delivered_at__isnull=True).update(
        delivered_at=F("sent_at")
    )


class Migration(migrations.Migration):
    dependencies = [
        ("search", "0003_add_delivered_at"),
    ]

    operations = [
        migrations.RunPython(
            backfill_delivered_at,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
