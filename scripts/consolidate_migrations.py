#!/usr/bin/env python3
"""Consolidate Django migration files by deleting old migrations.

This script deletes migration files for apps that exceed a threshold count,
then prints instructions for regenerating a fresh initial migration.

Usage:
    uv run python scripts/consolidate_migrations.py
    uv run python scripts/consolidate_migrations.py --threshold 5
    uv run python scripts/consolidate_migrations.py --force
    uv run python scripts/consolidate_migrations.py --apps-dir src/backend/apps
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consolidate Django migration files by deleting old migrations."
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=8,
        help="Max migration files per app before consolidation triggers (default: 8)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Consolidate all apps regardless of threshold",
    )
    parser.add_argument(
        "--apps-dir",
        type=str,
        default="src/backend/apps",
        help="Path to apps directory (default: src/backend/apps)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    return parser.parse_args()


def _check_git_status(apps_dir: str) -> bool:
    """Check git status and warn if uncommitted model changes exist.

    Returns True if the working tree is clean (no uncommitted changes),
    False if there are uncommitted changes.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stdout.strip():
            print(
                "WARNING: Uncommitted changes detected in git working tree.\n"
                "It is recommended to commit or stash changes before consolidation.",
                file=sys.stderr,
            )
            return False
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        print("WARNING: Could not check git status (not a git repository?).", file=sys.stderr)
        return False


def _count_migration_files(migrations_dir: Path) -> int:
    """Count migration files matching [0-9]*.py pattern."""
    count = 0
    for entry in migrations_dir.iterdir():
        if entry.is_file() and entry.name.endswith(".py") and entry.name[0].isdigit():
            count += 1
    return count


def _delete_migration_files(migrations_dir: Path, app_name: str, dry_run: bool) -> int:
    """Delete all [0-9]*.py migration files and __pycache__.

    Returns the number of files deleted.
    """
    deleted = 0

    for entry in sorted(migrations_dir.iterdir()):
        if entry.is_file() and entry.name.endswith(".py") and entry.name[0].isdigit():
            if dry_run:
                print(f"  Would delete: {entry.relative_to(migrations_dir.parent.parent)}")
            else:
                entry.unlink()
                print(f"  Deleted: {entry.relative_to(migrations_dir.parent.parent)}")
            deleted += 1

    # Clean __pycache__ inside migrations/
    pycache = migrations_dir / "__pycache__"
    if pycache.exists() and pycache.is_dir():
        if dry_run:
            print(f"  Would remove: {pycache}")
        else:
            shutil.rmtree(pycache)
            print(f"  Removed: {pycache}")

    return deleted


def main() -> None:
    args = _parse_args()
    apps_dir = Path(args.apps_dir)

    if not apps_dir.exists() or not apps_dir.is_dir():
        print(f"Error: apps directory not found: {apps_dir}", file=sys.stderr)
        sys.exit(1)

    # Optional git status check
    _check_git_status(str(apps_dir))

    apps_to_consolidate: list[str] = []
    total_deleted = 0

    # Walk all app directories
    for app_entry in sorted(apps_dir.iterdir()):
        if not app_entry.is_dir():
            continue

        migrations_dir = app_entry / "migrations"
        if not migrations_dir.exists() or not migrations_dir.is_dir():
            continue

        count = _count_migration_files(migrations_dir)
        app_name = app_entry.name

        should_consolidate = args.force or count > args.threshold

        if should_consolidate:
            print(f"\n--- {app_name} ({count} migration files) ---")
            apps_to_consolidate.append(app_name)
            deleted = _delete_migration_files(migrations_dir, app_name, args.dry_run)
            total_deleted += deleted
        else:
            print(f"  {app_name}: {count} files — under threshold ({args.threshold}), skipped")

    # Summary
    print("\n" + "=" * 60)
    print("Consolidation summary:")
    print(f"  Apps consolidated: {len(apps_to_consolidate)}")
    print(f"  Files deleted:     {total_deleted}")
    if apps_to_consolidate:
        print(f"  Apps:              {', '.join(apps_to_consolidate)}")

    # Next steps instructions
    if apps_to_consolidate:
        print("\nNext steps:")
        print("  1. Run: uv run python src/backend/manage.py makemigrations")
        print("  2. Run: uv run python src/backend/manage.py migrate")
        print("  3. If applying to an existing database, use:")
        print("     uv run python src/backend/manage.py migrate --fake-initial")
        print("\nAfter confirming everything works:")
        print("  4. Commit the new migration files")

    if args.dry_run:
        print("\nDry-run complete. No files were actually deleted.")


if __name__ == "__main__":
    main()