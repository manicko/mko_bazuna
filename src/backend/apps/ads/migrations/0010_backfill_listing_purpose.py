"""Backfill listing_purpose for existing ads — assigns 'sell' as default."""

from django.db import migrations


def backfill_listing_purpose(apps, schema_editor):
    """Assign the 'sell' listing purpose to all existing ads without one.

    Creates the 'sell' LookupItem in the listing_purpose group if it does
    not already exist, making this migration self-contained and independent
    of the catalog data migration order.
    """
    LookupGroup = apps.get_model("lookups", "LookupGroup")
    LookupItem = apps.get_model("lookups", "LookupItem")
    Ad = apps.get_model("ads", "Ad")

    # Get or create the listing_purpose group
    group, _ = LookupGroup.objects.get_or_create(
        code="listing_purpose",
        defaults={
            "name_i18n": {
                "ru": "Цель объявления",
                "bs": "Svrha oglasa",
                "en": "Listing purpose",
            },
            "is_system": True,
            "sort_order": 1,
        },
    )

    # Get or create the 'sell' purpose
    sell_item, _ = LookupItem.objects.get_or_create(
        slug="sell",
        defaults={
            "group": group,
            "name_i18n": {
                "ru": "Продажа",
                "bs": "Prodaja",
                "en": "Sell",
            },
            "sort_order": 1,
            "is_active": True,
        },
    )

    # Assign sell to all ads without a listing_purpose
    updated = Ad.objects.filter(listing_purpose__isnull=True).update(
        listing_purpose=sell_item
    )
    if updated:
        print(f"  Backfilled listing_purpose for {updated} ad(s) with 'sell'")


class Migration(migrations.Migration):
    """Data migration: assign 'sell' listing purpose to all existing ads."""

    dependencies = [
        ("ads", "0009_ad_listing_purpose"),
        ("lookups", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            backfill_listing_purpose,
            reverse_code=migrations.RunPython.noop,
        ),
    ]