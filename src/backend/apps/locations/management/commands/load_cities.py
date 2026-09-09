"""Management command to load city reference data from cities.json fixture.

Reuses the canonical cities.json fixture maintained by the seed app
(apps/seed/fixtures/cities.json — 15 Montenegrin cities). The loader logic
is duplicated here (deserialize + bulk_create with update_conflicts) rather
than imported from SeedService, because seed imports locations models —
importing seed back from locations would invert the dependency direction.
"""

import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.core.enums import AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock
from apps.locations.models import City

logger = logging.getLogger(__name__)

# Reuse the existing cities.json fixture from the seed app (15 ME cities).
# From this file (apps/locations/management/commands/) → parents[3] = apps/,
# then descend into seed/fixtures/ to match seed_service.py:36 (FIXTURES_DIR).
CITIES_JSON_PATH = (
    Path(__file__).resolve().parents[3] / "seed" / "fixtures" / "cities.json"
)


class Command(BaseCommand):
    """Load city reference data from cities.json (idempotent, locked)."""

    help = "Load city reference data from cities.json fixture"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--config",
            type=str,
            default=str(CITIES_JSON_PATH),
            help=f"Path to cities JSON fixture (default: {CITIES_JSON_PATH})",
        )

    def handle(self, *args, **options) -> None:
        config_path = Path(options["config"])

        self.stdout.write(f"Loading cities from: {config_path}")

        with advisory_lock(AdvisoryLockId.CATALOG_LOAD, session=True):
            self._load_cities(config_path)

    def _load_cities(self, config_path: Path) -> None:
        from django.core.serializers import deserialize

        if not config_path.exists():
            raise CommandError(f"Cities fixture not found: {config_path}")

        with open(config_path, encoding="utf-8") as f:
            data = f.read()

        objs: list[City] = [
            deserialized.object for deserialized in deserialize("json", data)
        ]

        City.objects.bulk_create(
            objs,
            update_conflicts=True,
            update_fields=["name", "region", "country_code", "name_i18n"],
            unique_fields=["slug"],
        )

        count = City.objects.count()
        logger.info(
            "Cities loaded: %d record(s) processed, %d total in DB",
            len(objs),
            count,
        )
        self.stdout.write(
            self.style.SUCCESS(f"Cities loaded — {len(objs)} record(s); {count} total")
        )
