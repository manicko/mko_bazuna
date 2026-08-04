"""Seed migration for categories — creates initial category tree using ORM."""
import json

from django.db import migrations

# MPTT tree structure (all in same tree, tree_id=1):
# Товары (root, level=0, lft=1, rght=12, spans 5 children)
#   Электроника (level=1, lft=2, rght=3)
#   Одежда (level=1, lft=4, rght=5)
#   Дом и сад (level=1, lft=6, rght=7)
#   Авто товары (level=1, lft=8, rght=9)
#   Спорт (level=1, lft=10, rght=11)
# Услуги (root, level=0, lft=13, rght=22, spans 4 children)
#   Ремонт (level=1, lft=14, rght=15)
#   Перевозки (level=1, lft=16, rght=17)
#   Образование (level=1, lft=18, rght=19)
#   Здоровье (level=1, lft=20, rght=21)
# Недвижимость (root, level=0, lft=23, rght=30, spans 3 children)
#   Квартиры (level=1, lft=24, rght=25)
#   Дома (level=1, lft=26, rght=27)
#   Коммерция (level=1, lft=28, rght=29)

SEED_CATEGORIES = [
    # Root: Товары
    {"name": "Товары", "name_i18n": '{"ru": "Товары", "bs": "Proizvodi"}', "slug": "tovary", "lft": 1, "rght": 12, "tree_id": 1, "level": 0, "parent": None, "is_active": True},
    # Children of Товары
    {"name": "Электроника", "name_i18n": '{"ru": "Электроника", "bs": "Elektronika"}', "slug": "elektronika", "lft": 2, "rght": 3, "tree_id": 1, "level": 1, "parent_slug": "tovary", "is_active": True},
    {"name": "Одежда", "name_i18n": '{"ru": "Одежда", "bs": "Odeća"}', "slug": "odezhda", "lft": 4, "rght": 5, "tree_id": 1, "level": 1, "parent_slug": "tovary", "is_active": True},
    {"name": "Дом и сад", "name_i18n": '{"ru": "Дом и сад", "bs": "Kuća i bašta"}', "slug": "dom", "lft": 6, "rght": 7, "tree_id": 1, "level": 1, "parent_slug": "tovary", "is_active": True},
    {"name": "Авто товары", "name_i18n": '{"ru": "Авто товары", "bs": "Proizvodi za automobile"}', "slug": "avto", "lft": 8, "rght": 9, "tree_id": 1, "level": 1, "parent_slug": "tovary", "is_active": True},
    {"name": "Спорт", "name_i18n": '{"ru": "Спорт", "bs": "Sport"}', "slug": "sport", "lft": 10, "rght": 11, "tree_id": 1, "level": 1, "parent_slug": "tovary", "is_active": True},
    # Root: Услуги
    {"name": "Услуги", "name_i18n": '{"ru": "Услуги", "bs": "Usluge"}', "slug": "uslugi", "lft": 13, "rght": 22, "tree_id": 1, "level": 0, "parent": None, "is_active": True},
    # Children of Услуги
    {"name": "Ремонт", "name_i18n": '{"ru": "Ремонт", "bs": "Popravka"}', "slug": "remont", "lft": 14, "rght": 15, "tree_id": 1, "level": 1, "parent_slug": "uslugi", "is_active": True},
    {"name": "Перевозки", "name_i18n": '{"ru": "Перевозки", "bs": "Prevoz"}', "slug": "perevozki", "lft": 16, "rght": 17, "tree_id": 1, "level": 1, "parent_slug": "uslugi", "is_active": True},
    {"name": "Образование", "name_i18n": '{"ru": "Образование", "bs": "Obrazovanje"}', "slug": "obrazovanie", "lft": 18, "rght": 19, "tree_id": 1, "level": 1, "parent_slug": "uslugi", "is_active": True},
    {"name": "Здоровье", "name_i18n": '{"ru": "Здоровье", "bs": "Zdravlje"}', "slug": "zdorovie", "lft": 20, "rght": 21, "tree_id": 1, "level": 1, "parent_slug": "uslugi", "is_active": True},
    # Root: Недвижимость
    {"name": "Недвижимость", "name_i18n": '{"ru": "Недвижимость", "bs": "Nekretnine"}', "slug": "nedvizhimost", "lft": 23, "rght": 30, "tree_id": 1, "level": 0, "parent": None, "is_active": True},
    # Children of Недвижимость
    {"name": "Квартиры", "name_i18n": '{"ru": "Квартиры", "bs": "Stanovi"}', "slug": "kvartiry", "lft": 24, "rght": 25, "tree_id": 1, "level": 1, "parent_slug": "nedvizhimost", "is_active": True},
    {"name": "Дома", "name_i18n": '{"ru": "Дома", "bs": "Kuće"}', "slug": "doma", "lft": 26, "rght": 27, "tree_id": 1, "level": 1, "parent_slug": "nedvizhimost", "is_active": True},
    {"name": "Коммерция", "name_i18n": '{"ru": "Коммерция", "bs": "Poslovni prostor"}', "slug": "kommercija", "lft": 28, "rght": 29, "tree_id": 1, "level": 1, "parent_slug": "nedvizhimost", "is_active": True},
]


def create_categories(apps, schema_editor):
    """Create seed categories with explicit MPTT tree structure.

    MPTT lft/rght/tree_id/level values are pre-computed to avoid depending
    on MPTT manager methods (which are unavailable for historical models).
    """
    Category = apps.get_model("categories", "Category")

    # Build slug -> instance map for parent FK resolution
    slug_map: dict[str, object] = {}

    for cat_data in SEED_CATEGORIES:
        parent_slug = cat_data.pop("parent_slug", None)
        parent = slug_map.get(parent_slug) if parent_slug else None

        category = Category.objects.create(
            name=cat_data["name"],
            name_i18n=cat_data["name_i18n"],
            slug=cat_data["slug"],
            lft=cat_data["lft"],
            rght=cat_data["rght"],
            tree_id=cat_data["tree_id"],
            level=cat_data["level"],
            parent=parent,
            is_active=cat_data["is_active"],
        )
        slug_map[cat_data["slug"]] = category


class Migration(migrations.Migration):
    dependencies = [
        ("categories", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_categories, migrations.RunPython.noop),
    ]