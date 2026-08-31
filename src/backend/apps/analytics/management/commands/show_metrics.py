"""
Management command to show analytics metrics.

Aggregates events by type and date, outputs to stdout.
"""

import logging
from datetime import timedelta

from apps.analytics.models import AnalyticsEvent
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Show analytics metrics aggregated by type and date."""

    help = "Show analytics metrics aggregated by event type and date"

    def add_arguments(self, parser):
        """Add days argument for filtering metrics."""
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days to include in metrics (default: 30)",
        )

    def handle(self, *args, **options):
        """Execute the metrics command."""
        days = options["days"]
        cutoff_date = timezone.now() - timedelta(days=days)

        self.stdout.write(
            self.style.MIGRATE_HEADING(f"Analytics Metrics (last {days} days)")
        )
        self.stdout.write("-" * 40)

        # Aggregate by event type
        self.stdout.write("\nEvents by type:")
        type_aggregates = (
            AnalyticsEvent.objects.filter(timestamp__gte=cutoff_date)
            .values("event_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        for item in type_aggregates:
            event_type = item["event_type"]
            count = item["count"]
            self.stdout.write(f"  {event_type}: {count}")

        # Aggregate by date
        self.stdout.write("\nEvents by date (last 7 days):")
        seven_days_ago = timezone.now() - timedelta(days=7)
        date_aggregates = (
            AnalyticsEvent.objects.filter(timestamp__gte=seven_days_ago)
            .annotate(date=TruncDate("timestamp"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        if not date_aggregates:
            self.stdout.write("  No events in the last 7 days")

        for item in date_aggregates:
            date = item["date"]
            count = item["count"]
            self.stdout.write(f"  {date}: {count}")

        # Summary
        total = AnalyticsEvent.objects.filter(timestamp__gte=cutoff_date).count()
        self.stdout.write("\n" + "-" * 40)
        self.stdout.write(f"Total events: {total}")
