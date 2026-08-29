"""Inject RunSQL trigger DDL into the squashed ads 0001_initial migration.

After ``makemigrations`` regenerates ``ads/0001_initial.py`` during a migration
squash, raw SQL DDL (PostgreSQL trigger functions and triggers) cannot be
re-derived from model state. This command re-injects them as
``migrations.RunSQL`` operations, sourcing the SQL from
``setup_search_triggers.DDL_STATEMENTS`` so the trigger definitions live in a
single place.

Idempotent: a ``# SQUASH_REHYDRATE: trigger DDL`` marker guards against
double-injection.
"""

import ast
import logging
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand

from apps.ads.management.commands.setup_search_triggers import DDL_STATEMENTS

logger = logging.getLogger(__name__)

MARKER = "# SQUASH_REHYDRATE: trigger DDL"
LIST_INDENT = "        "  # 8 spaces; the body of `operations = [...]`


def _render_runsql_block() -> list[str]:
    """Render the marker comment plus one RunSQL operation per DDL statement.

    SQL is embedded via ``repr()`` so dollar-quoted bodies (``$$``) and quote
    characters survive as a single valid string literal rather than risking
    f-string interpolation of the SQL content itself.
    """
    block: list[str] = [MARKER]
    for _label, sql in DDL_STATEMENTS:
        block.append(
            f"migrations.RunSQL(sql={sql!r}, reverse_sql=migrations.RunSQL.noop),"
        )
    return [f"{LIST_INDENT}{line}" for line in block]


def _find_operations_end_lineno(source: str) -> int | None:
    """Return the 1-based closing line of ``operations = [...]`` in Migration."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == "Migration"):
            continue
        for child in node.body:
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name) and target.id == "operations":
                        return child.end_lineno
    return None


class Command(BaseCommand):
    """Re-inject trigger/function RunSQL into the squashed ads migration."""

    help = (
        "Inject migrations.RunSQL trigger DDL (from setup_search_triggers) into "
        "the squashed ads/0001_initial.py migration"
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the RunSQL operations that would be injected; write nothing.",
        )

    def handle(self, *args, **options) -> None:
        """Locate the migration, splice in RunSQL ops before the closing ``]``."""
        dry_run: bool = options["dry_run"]

        ads_config = apps.get_app_config("ads")
        migration_path = Path(ads_config.path) / "migrations" / "0001_initial.py"
        if not migration_path.exists():
            self.stderr.write(
                self.style.ERROR(f"Migration not found: {migration_path}")
            )
            return

        source = migration_path.read_text()

        if MARKER in source:
            logger.info("Marker present in %s; skipping injection", migration_path)
            self.stdout.write(
                self.style.SUCCESS(f"RunSQL DDL already present in {migration_path}")
            )
            return

        end_lineno = _find_operations_end_lineno(source)
        if end_lineno is None:
            self.stderr.write(
                self.style.ERROR("Could not locate `operations = [...]` in Migration")
            )
            return

        block_lines = _render_runsql_block()
        injected = [f"{line}\n" for line in block_lines]

        file_lines = source.splitlines(keepends=True)
        # end_lineno is 1-based; insert just before the "]" line that closes the
        # operations list so the RunSQL calls land inside it.
        insert_at = end_lineno - 1
        result = "".join([*file_lines[:insert_at], *injected, *file_lines[insert_at:]])

        if dry_run:
            logger.info(
                "Dry run: would inject %d RunSQL ops into %s",
                len(DDL_STATEMENTS),
                migration_path,
            )
            self.stdout.write(
                self.style.NOTICE(f"Dry run - would inject into {migration_path}:")
            )
            for line in block_lines:
                self.stdout.write(line)
            return

        migration_path.write_text(result)
        logger.info(
            "Injected %d RunSQL ops into %s", len(DDL_STATEMENTS), migration_path
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Injected {len(DDL_STATEMENTS)} RunSQL operations into {migration_path}"
            )
        )
