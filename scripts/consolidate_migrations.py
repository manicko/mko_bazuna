#!/usr/bin/env python3
"""Consolidate Django migration files by deleting old migrations.

This script deletes migration files for apps that exceed a threshold count,
then prints instructions for regenerating a fresh initial migration.

Usage:
    uv run python scripts/consolidate_migrations.py
    uv run python scripts/consolidate_migrations.py --threshold 5
    uv run python scripts/consolidate_migrations.py --force
    uv run python scripts/consolidate_migrations.py --apps-dir src/backend/apps
    uv run python scripts/consolidate_migrations.py --inventory
    uv run python scripts/consolidate_migrations.py --inventory --inventory-output manifest.json
"""

import argparse
import ast
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
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
    parser.add_argument(
        "--inventory",
        "-i",
        action="store_true",
        help="Scan migration files and emit a manifest of non-auto-generated "
        "operations (RunSQL, RunPython, SeparateDatabaseAndState, "
        "AddIndex with concurrent=True) without deleting anything.",
    )
    parser.add_argument(
        "--inventory-output",
        type=str,
        default=None,
        help="Write the inventory manifest to this file (JSON) in addition to stdout.",
    )
    args = parser.parse_args()
    if args.inventory and (args.force or args.dry_run):
        parser.error("--inventory is mutually exclusive with --force and --dry-run")
    return args


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


# ---------------------------------------------------------------------------
# Migration inventory (--inventory)
#
# Walks pre-consolidation migration files and emits a manifest of the hand-
# written, non-auto-generated operations that must survive a squash: RunSQL,
# RunPython, SeparateDatabaseAndState, and AddIndex(concurrent=True).
# ---------------------------------------------------------------------------


_MONITORED_OPS: tuple[str, ...] = (
    "RunSQL",
    "RunPython",
    "SeparateDatabaseAndState",
    "AddIndex",
)


@dataclass
class OperationEntry:
    op_type: str
    location: str
    sql: str | None = None
    function: str | None = None
    idempotent: str | None = None


@dataclass
class FileInventory:
    app: str
    migration: str
    file: str
    operations: list[OperationEntry]


@dataclass
class InventoryManifest:
    apps_dir: str
    files_scanned: int
    files_with_operations: int
    summary: dict[str, int]
    total_operations: int
    files: list[FileInventory]


def _collect_module_constants(tree: ast.Module) -> dict[str, ast.AST]:
    """Map module-level ``NAME = value`` assignments for variable resolution."""
    constants: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = node.value
    return constants


def _find_migration_class(tree: ast.Module) -> ast.ClassDef | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Migration":
            return node
    return None


def _find_operations_list(migration_class: ast.ClassDef) -> ast.List | None:
    for stmt in migration_class.body:
        target: ast.AST | None
        value: ast.AST | None
        if isinstance(stmt, ast.Assign):
            target, value = stmt.targets[0], stmt.value
        elif isinstance(stmt, ast.AnnAssign):
            target, value = stmt.target, stmt.value
        else:
            continue
        if (
            isinstance(target, ast.Name)
            and target.id == "operations"
            and isinstance(value, ast.List)
        ):
            return value
    return None


def _call_op_type(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _resolve_sql_value(node: ast.AST, constants: dict[str, ast.AST]) -> str | None:
    """Resolve a RunSQL ``sql`` argument to its string content where possible."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, (ast.Tuple, ast.List)):
        parts = [
            part
            for part in (_resolve_sql_value(elt, constants) for elt in node.elts)
            if part
        ]
        return "".join(parts) or None
    if isinstance(node, ast.Name) and node.id in constants:
        return _resolve_sql_value(constants[node.id], constants)
    return None


def _runsql_sql(call: ast.Call, constants: dict[str, ast.AST]) -> str | None:
    if call.args:
        return _resolve_sql_value(call.args[0], constants)
    for kw in call.keywords:
        if kw.arg == "sql":
            return _resolve_sql_value(kw.value, constants)
    return None


def _runpython_function(call: ast.Call) -> str | None:
    if call.args and isinstance(call.args[0], ast.Name):
        return call.args[0].id
    return None


def _is_concurrent_addindex(call: ast.Call) -> bool:
    for kw in call.keywords:
        if (
            kw.arg == "concurrent"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is True
        ):
            return True
    return False


def _classify_idempotency(sql: str | None) -> str | None:
    """Classify forward-run idempotency of a RunSQL statement.

    - ``CREATE OR REPLACE`` / ``DROP TRIGGER IF EXISTS`` -> forward idempotent.
    - ``CREATE INDEX CONCURRENTLY`` with ``IF NOT EXISTS`` -> forward idempotent.
    - ``CREATE INDEX CONCURRENTLY`` without ``IF NOT EXISTS`` -> not idempotent.
    - Anything else -> unknown (no static guarantee).
    """
    if sql is None:
        return None
    upper = sql.upper()
    if "CREATE OR REPLACE" in upper or "DROP TRIGGER IF EXISTS" in upper:
        return "forward_idempotent"
    if "CREATE INDEX CONCURRENTLY" in upper:
        return "forward_idempotent" if "IF NOT EXISTS" in upper else "not_idempotent"
    return "unknown"


def _descend_sdbs(
    call: ast.Call,
    location: str,
    constants: dict[str, ast.AST],
    entries: list[OperationEntry],
) -> None:
    """Recurse into SeparateDatabaseAndState database_state/state_operations."""
    for kw in call.keywords:
        if kw.arg in ("database_operations", "state_operations") and isinstance(
            kw.value, ast.List
        ):
            for j, sub in enumerate(kw.value.elts):
                _collect_from_call(sub, f"{location}.{kw.arg}[{j}]", constants, entries)


def _collect_from_call(
    node: ast.AST,
    location: str,
    constants: dict[str, ast.AST],
    entries: list[OperationEntry],
) -> None:
    if not isinstance(node, ast.Call):
        return
    op_type = _call_op_type(node)
    if op_type is None:
        return
    if op_type == "RunSQL":
        sql = _runsql_sql(node, constants)
        entries.append(
            OperationEntry(
                op_type="RunSQL",
                location=location,
                sql=sql,
                idempotent=_classify_idempotency(sql),
            )
        )
        return
    if op_type == "RunPython":
        entries.append(
            OperationEntry(
                op_type="RunPython",
                location=location,
                function=_runpython_function(node),
            )
        )
        return
    if op_type == "AddIndex":
        if _is_concurrent_addindex(node):
            entries.append(OperationEntry(op_type="AddIndex", location=location))
        return
    if op_type == "SeparateDatabaseAndState":
        entries.append(
            OperationEntry(op_type="SeparateDatabaseAndState", location=location)
        )
        _descend_sdbs(node, location, constants, entries)
        return


def _collect_migration_operations(
    tree: ast.Module, constants: dict[str, ast.AST]
) -> list[OperationEntry]:
    migration_class = _find_migration_class(tree)
    if migration_class is None:
        return []
    operations_list = _find_operations_list(migration_class)
    if operations_list is None:
        return []
    entries: list[OperationEntry] = []
    for i, op in enumerate(operations_list.elts):
        _collect_from_call(op, f"operations[{i}]", constants, entries)
    return entries


def _scan_inventory(apps_dir: Path) -> InventoryManifest:
    """Walk ``apps/<app>/migrations/0*.py`` and inventory hand-written operations."""
    summary: dict[str, int] = {op: 0 for op in _MONITORED_OPS}
    files_scanned = 0
    files_with_operations = 0
    file_inventories: list[FileInventory] = []

    for app_entry in sorted(apps_dir.iterdir()):
        if not app_entry.is_dir():
            continue
        migrations_dir = app_entry / "migrations"
        if not migrations_dir.exists() or not migrations_dir.is_dir():
            continue
        for migration_file in sorted(migrations_dir.iterdir()):
            if (
                not migration_file.is_file()
                or not migration_file.name.endswith(".py")
                or not migration_file.name[0].isdigit()
            ):
                continue
            files_scanned += 1
            source = migration_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source, filename=str(migration_file))
            except SyntaxError as exc:
                print(
                    f"WARNING: could not parse {migration_file}: {exc}",
                    file=sys.stderr,
                )
                continue
            constants = _collect_module_constants(tree)
            entries = _collect_migration_operations(tree, constants)
            if not entries:
                continue
            files_with_operations += 1
            for entry in entries:
                summary[entry.op_type] = summary.get(entry.op_type, 0) + 1
            file_inventories.append(
                FileInventory(
                    app=app_entry.name,
                    migration=migration_file.stem,
                    file=str(migration_file.relative_to(apps_dir)),
                    operations=entries,
                )
            )

    return InventoryManifest(
        apps_dir=str(apps_dir),
        files_scanned=files_scanned,
        files_with_operations=files_with_operations,
        summary=summary,
        total_operations=sum(summary.values()),
        files=file_inventories,
    )


def _print_inventory_summary(manifest: InventoryManifest) -> None:
    print("Inventory scan complete.")
    print(f"Apps directory: {manifest.apps_dir}")
    print(f"Files scanned: {manifest.files_scanned}")
    print(f"Files with monitored operations: {manifest.files_with_operations}")
    print("\nOperation counts:")
    for op_type, count in manifest.summary.items():
        print(f"  {op_type}: {count}")
    print(
        f"\nTotal monitored operations: {manifest.total_operations} "
        f"across {manifest.files_with_operations} files"
    )


def main() -> None:
    args = _parse_args()
    apps_dir = Path(args.apps_dir)

    if not apps_dir.exists() or not apps_dir.is_dir():
        print(f"Error: apps directory not found: {apps_dir}", file=sys.stderr)
        sys.exit(1)

    if args.inventory:
        manifest = _scan_inventory(apps_dir)
        _print_inventory_summary(manifest)
        if args.inventory_output:
            out_path = Path(args.inventory_output)
            out_path.write_text(
                json.dumps(asdict(manifest), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"\nManifest written to: {out_path}")
        sys.exit(0)

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