"""
Catalog builder — loads categories, lookups, and bindings from a YAML config file.

Supports:
- Idempotent update_or_create by slug
- Rename via new_slug with slug_rename_map auto-resolution
- category_paths reference resolution through renamed slugs
- Auto-rewrite YAML after rename (removes new_slug, updates slug)
- Deferred categories (skipped, kept in config for documentation)
- Level-by-level category tree insertion via MPTT insert_at()
"""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def load_catalog(config_path: str | Path) -> dict[str, str]:
    """Load catalog from YAML config. Creates/updates all records.

    Order of operations:
    1. LookupGroup + LookupItem
    2. Category tree (L1 -> L2 -> L3 -> L4)
    3. CategoryListingPurpose + CategoryListingFeature
    4. CategoryPath

    Args:
        config_path: Path to categories.yaml file.

    Returns:
        slug_rename_map: {old_slug: new_slug} for any renames that occurred.

    Raises:
        FileNotFoundError: If config_path does not exist.
        yaml.YAMLError: If YAML is malformed.
    """
    from django.db import transaction

    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Catalog config not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        logger.warning("Empty catalog config at %s", config_path)
        return {}

    slug_rename_map: dict[str, str] = {}

    with transaction.atomic():
        # Phase 1: Load lookups
        group_map = _load_lookups(data.get("lookups", {}))

        # Phase 2: Load category tree
        category_map = _load_categories(
            data.get("categories", []),
            group_map,
            slug_rename_map,
        )

        # Phase 3: Load bindings
        _load_bindings(data.get("categories", []), category_map, group_map)

        # Phase 4: Load category paths
        _load_category_paths(
            data.get("category_paths", []),
            category_map,
            slug_rename_map,
        )

    # Auto-rewrite YAML if renames occurred
    if slug_rename_map:
        _rewrite_yaml(config_path, slug_rename_map)

    return slug_rename_map


def _load_lookups(data: dict) -> dict[str, Any]:
    """Create/update LookupGroup and LookupItem records.

    Args:
        data: Dict mapping group_code -> list of item dicts.

    Returns:
        group_map: {group_code: group_instance}
    """
    from apps.lookups.models import LookupGroup, LookupItem

    group_map: dict[str, Any] = {}

    for group_code, items_data in data.items():
        group, _ = LookupGroup.objects.update_or_create(
            code=group_code,
            defaults={
                "is_system": True,
            },
        )
        group_map[group_code] = group

        if items_data:
            for idx, item_data in enumerate(items_data):
                LookupItem.objects.update_or_create(
                    slug=item_data["slug"],
                    defaults={
                        "group": group,
                        "name_i18n": item_data.get("name_i18n"),
                        "sort_order": item_data.get("sort_order", idx + 1),
                        "is_active": item_data.get("is_active", True),
                        "icon": item_data.get("icon", ""),
                        "color": item_data.get("color", ""),
                    },
                )

    logger.info("Loaded %d lookup groups", len(group_map))
    return group_map


def _load_categories(
    categories_data: list,
    group_map: dict[str, Any],
    slug_rename_map: dict[str, str],
) -> dict[str, Any]:
    """Create/update Category tree level by level.

    Processes levels L1 -> L2 -> L3 -> L4 so parents exist before children.
    Uses MPTT insert_at() for tree insertion.

    Args:
        categories_data: List of top-level category dicts.
        group_map: {group_code: group_instance}
        slug_rename_map: {old_slug: new_slug} — populated during renames.

    Returns:
        category_map: {slug: category_instance} for all categories.
    """
    from apps.categories.models import Category

    category_map: dict[str, Any] = {}

    def _process_level(
        items: list,
        parent: Any | None,
        level: int,
    ) -> None:
        """Recursively process categories at one level of the tree."""
        for item in items:
            slug = item["slug"]
            new_slug = item.get("new_slug")

            if item.get("deferred", False):
                logger.info("Skipping deferred category: %s", slug)
                # Still track parentless deferred cats so their children can reference them
                if parent is None:
                    category_map[slug] = None  # Placeholder
                continue

            update_slug = new_slug or slug

            # Track rename
            if new_slug:
                slug_rename_map[slug] = new_slug

            resolved_parent: Any = None
            if parent is not None:
                resolved_parent = parent

            category, created = Category.objects.update_or_create(
                slug=slug,  # Match by original slug
                defaults={
                    "slug": update_slug,  # Write new slug if renamed
                    "name": item.get("name", item["name"]),
                    "name_i18n": item.get("name_i18n"),
                    "is_active": item.get("is_active", True),
                },
            )

            # Insert into MPTT tree if newly created (has no parent yet)
            if created and resolved_parent is not None:
                category.parent = resolved_parent
                category.save()

            category_map[update_slug] = category

            # Process children
            children_data = item.get("children", [])
            if children_data:
                _process_level(children_data, category, level + 1)

    _process_level(categories_data, None, 1)
    logger.info("Loaded %d categories", len(category_map))
    return category_map


def _load_bindings(
    categories_data: list,
    category_map: dict[str, Any],
    group_map: dict[str, Any],
) -> None:
    """Create/update CategoryListingPurpose and CategoryListingFeature.

    Args:
        categories_data: List of top-level category dicts.
        category_map: {slug: category_instance}
        group_map: {group_code: group_instance}
    """
    from apps.categories.models import CategoryListingFeature, CategoryListingPurpose
    from apps.lookups.models import LookupItem

    count_purposes = 0
    count_features = 0

    def _process_bindings(items: list) -> None:
        nonlocal count_purposes, count_features

        for item in items:
            slug = item.get("new_slug") or item["slug"]
            category = category_map.get(slug)
            if category is None:
                continue

            # Bind listing purposes
            purpose_overrides = item.get("listing_purpose_override", [])
            if purpose_overrides:
                for ps_slug in purpose_overrides:
                    try:
                        purpose_item = LookupItem.objects.get(
                            slug=ps_slug,
                            group__code="listing_purpose",
                        )
                        CategoryListingPurpose.objects.update_or_create(
                            category=category,
                            listing_purpose=purpose_item,
                        )
                        count_purposes += 1
                    except LookupItem.DoesNotExist:
                        logger.warning(
                            "Listing purpose slug not found: %s", ps_slug
                        )

            # Bind listing features
            feature_overrides = item.get("listing_feature_override", [])
            if feature_overrides:
                for f_slug in feature_overrides:
                    try:
                        feature_item = LookupItem.objects.get(
                            slug=f_slug,
                            group__code="listing_feature",
                        )
                        CategoryListingFeature.objects.update_or_create(
                            category=category,
                            feature=feature_item,
                        )
                        count_features += 1
                    except LookupItem.DoesNotExist:
                        logger.warning(
                            "Listing feature slug not found: %s", f_slug
                        )

            # Process children recursively (inherit or override)
            children_data = item.get("children", [])
            if children_data:
                _process_bindings(children_data)

    _process_bindings(categories_data)
    logger.info("Loaded %d purpose bindings, %d feature bindings", count_purposes, count_features)


def _load_category_paths(
    paths_data: list,
    category_map: dict[str, Any],
    slug_rename_map: dict[str, str],
) -> None:
    """Create/update CategoryPath records.

    Resolves old/new slugs via _resolve_slug() using slug_rename_map.

    Args:
        paths_data: List of {category: slug, parent: slug} dicts.
        category_map: {slug: category_instance}
        slug_rename_map: {old_slug: new_slug}
    """
    from apps.categories.models import CategoryPath

    def _resolve_slug(slug: str) -> str:
        """Resolve a slug through the rename map."""
        return slug_rename_map.get(slug, slug)

    count = 0
    for path_entry in paths_data:
        cat_slug = _resolve_slug(path_entry["category"])
        parent_slug = _resolve_slug(path_entry["parent"])

        category = category_map.get(cat_slug)
        parent = category_map.get(parent_slug)

        if category is None or parent is None:
            logger.warning(
                "Cannot create CategoryPath: category=%s, parent=%s (not found)",
                cat_slug,
                parent_slug,
            )
            continue

        CategoryPath.objects.update_or_create(
            category=category,
            parent=parent,
            defaults={
                "sort_order": path_entry.get("sort_order", 0),
                "is_automatic": path_entry.get("is_automatic", False),
            },
        )
        count += 1

    logger.info("Loaded %d category paths", count)


def _rewrite_yaml(config_path: Path, slug_rename_map: dict[str, str]) -> None:
    """Rewrite the YAML file to remove new_slug fields and update slugs.

    After a successful run that consumed new_slug values, this removes the
    new_slug field from each renamed entry and sets slug to the new value.
    Writes to a temp file, then atomically replaces the original.

    Args:
        config_path: Path to the YAML config file.
        slug_rename_map: {old_slug: new_slug}
    """
    if not slug_rename_map:
        return

    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        logger.warning("Cannot read YAML for rewrite: %s", e)
        return

    old_to_new = slug_rename_map

    def _rewrite_node(node: dict) -> dict | None:
        """Recursively rewrite a category/dict node, removing new_slug."""
        slug = node.get("slug")
        new_slug = node.get("new_slug")

        if new_slug and slug in old_to_new:
            node["slug"] = new_slug
            del node["new_slug"]

        # Recursively process children
        children = node.get("children", [])
        if children:
            node["children"] = [
                _rewrite_node(child) for child in children
            ]

        return node

    # Rewrite lookups (no renames for lookups currently, but handle anyway)
    lookups = data.get("lookups", {})
    for _group_code, items in lookups.items():
        if items:
            for item in items:
                _rewrite_node(item)

    # Rewrite categories
    categories = data.get("categories", [])
    if categories:
        data["categories"] = [
            _rewrite_node(cat) for cat in categories
        ]

    # Rewrite category_paths (slugs already resolved in DB, just update YAML refs)
    paths = data.get("category_paths", [])
    if paths:
        for path_entry in paths:
            cat_slug = path_entry.get("category")
            parent_slug = path_entry.get("parent")
            if cat_slug in old_to_new:
                path_entry["category"] = old_to_new[cat_slug]
            if parent_slug in old_to_new:
                path_entry["parent"] = old_to_new[parent_slug]

    # Write to temp file, then atomically replace
    try:
        fd, tmp_path = tempfile.mkstemp(
            suffix=".yaml",
            dir=str(config_path.parent),
        )
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            yaml.dump(data, tmp, default_flow_style=False, allow_unicode=True, sort_keys=False)
        shutil.copymode(str(config_path), tmp_path)
        os.replace(tmp_path, str(config_path))
        logger.info("Rewrote YAML config at %s (%d renames)", config_path, len(old_to_new))
    except (OSError, PermissionError) as e:
        logger.warning("Cannot rewrite YAML config: %s", e)