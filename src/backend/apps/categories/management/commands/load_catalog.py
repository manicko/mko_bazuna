"""Management command to load catalog from YAML config."""

from django.core.management.base import BaseCommand

from apps.categories.catalog import builder

CONFIG_PATH = "src/backend/apps/categories/catalog/categories.yaml"


class Command(BaseCommand):
    """Load catalog from YAML config into the database."""

    help = "Load catalog from YAML config"

    def add_arguments(self, parser):
        parser.add_argument(
            "--config",
            type=str,
            default=CONFIG_PATH,
            help=f"Path to catalog YAML config (default: {CONFIG_PATH})",
        )
        parser.add_argument(
            "--no-rewrite",
            action="store_true",
            help="Suppress YAML rewrite after rename operations",
        )

    def handle(self, *args, **options):
        config_path = options["config"]
        no_rewrite = options["no_rewrite"]

        self.stdout.write(f"Loading catalog from: {config_path}")

        slug_rename_map = builder.load_catalog(
            config_path,
            apps=None,
            rewrite_yaml=not no_rewrite,
        )

        if slug_rename_map:
            self.stdout.write(
                self.style.WARNING(
                    f"Renames applied: {len(slug_rename_map)} slug(s) updated"
                )
            )
            for old, new in slug_rename_map.items():
                self.stdout.write(f"  {old} -> {new}")
        else:
            self.stdout.write(self.style.SUCCESS("Catalog loaded successfully — no renames"))