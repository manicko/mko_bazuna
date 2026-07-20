# Seed migration for categories

from django.db import migrations


def create_categories(apps, schema_editor):
    """Create seed categories with proper MPTT tree structure."""
    # MPTT tree structure (all in same tree, tree_id=1):
    # lft=1,2 -> Товары (root, level=0, rght=12)
    #   lft=2,3 -> Электроника (child, level=1)
    #   lft=4,5 -> Одежда
    #   lft=6,7 -> Дом и сад
    #   lft=8,9 -> Авто товары
    #   lft=10,11 -> Спорт
    # lft=13,22 -> Услуги (root, level=0)
    #   lft=14,15 -> Ремонт
    #   lft=16,17 -> Перевозки
    #   lft=18,19 -> Образование
    #   lft=20,21 -> Здоровье
    # lft=23,30 -> Недвижимость (root, level=0)
    #   lft=24,25 -> Квартиры
    #   lft=26,27 -> Дома
    #   lft=28,29 -> Коммерция

    with schema_editor.connection.cursor() as cursor:
        # SQLite: disable foreign keys temporarily
        cursor.execute("PRAGMA foreign_keys = OFF")

        # Root: Товары (id=1) - lft=1, rght=12 means it spans 5 children
        cursor.execute(
            "INSERT INTO categories (name, name_i18n, slug, lft, rght, tree_id, level, is_active) "
            "VALUES (%s, %s, %s, 1, 12, 1, 0, 1)",
            ["Товары", '{"ru": "Товары", "bs": "Proizvodi"}', "tovary"],
        )
        # Children of Товары
        cursor.execute(
            "INSERT INTO categories (name, name_i18n, slug, parent_id, lft, rght, tree_id, level, is_active) "
            "VALUES (%s, %s, %s, 1, 2, 3, 1, 1, 1)",
            ["Электроника", '{"ru": "Электроника", "bs": "Elektronika"}', "elektronika"],
        )
        cursor.execute(
            "INSERT INTO categories (name, name_i18n, slug, parent_id, lft, rght, tree_id, level, is_active) "
            "VALUES (%s, %s, %s, 1, 4, 5, 1, 1, 1)",
            ["Одежда", '{"ru": "Одежда", "bs": "Odeća"}', "odezhda"],
        )
        cursor.execute(
            "INSERT INTO categories (name, name_i18n, slug, parent_id, lft, rght, tree_id, level, is_active) "
            "VALUES (%s, %s, %s, 1, 6, 7, 1, 1, 1)",
            ["Дом и сад", '{"ru": "Дом и сад", "bs": "Kuća i bašta"}', "dom"],
        )
        cursor.execute(
            "INSERT INTO categories (name, name_i18n, slug, parent_id, lft, rght, tree_id, level, is_active) "
            "VALUES (%s, %s, %s, 1, 8, 9, 1, 1, 1)",
            ["Авто товары", '{"ru": "Авто товары", "bs": "Proizvodi za automobile"}', "avto"],
        )
        cursor.execute(
            "INSERT INTO categories (name, name_i18n, slug, parent_id, lft, rght, tree_id, level, is_active) "
            "VALUES (%s, %s, %s, 1, 10, 11, 1, 1, 1)",
            ["Спорт", '{"ru": "Спорт", "bs": "Sport"}', "sport"],
        )

        # Root: Услуги (id=7) - lft=13, rght=22
        cursor.execute(
            "INSERT INTO categories (name, name_i18n, slug, lft, rght, tree_id, level, is_active) "
            "VALUES (%s, %s, %s, 13, 22, 1, 0, 1)",
            ["Услуги", '{"ru": "Услуги", "bs": "Usluge"}', "uslugi"],
        )
        cursor.execute(
            "INSERT INTO categories (name, name_i18n, slug, parent_id, lft, rght, tree_id, level, is_active) "
            "VALUES (%s, %s, %s, 7, 14, 15, 1, 1, 1)",
            ["Ремонт", '{"ru": "Ремонт", "bs": "Popravka"}', "remont"],
        )
        cursor.execute(
            "INSERT INTO categories (name, name_i18n, slug, parent_id, lft, rght, tree_id, level, is_active) "
            "VALUES (%s, %s, %s, 7, 16, 17, 1, 1, 1)",
            ["Перевозки", '{"ru": "Перевозки", "bs": "Prevoz"}', "perevozki"],
        )
        cursor.execute(
            "INSERT INTO categories (name, name_i18n, slug, parent_id, lft, rght, tree_id, level, is_active) "
            "VALUES (%s, %s, %s, 7, 18, 19, 1, 1, 1)",
            ["Образование", '{"ru": "Образование", "bs": "Obrazovanje"}', "obrazovanie"],
        )
        cursor.execute(
            "INSERT INTO categories (name, name_i18n, slug, parent_id, lft, rght, tree_id, level, is_active) "
            "VALUES (%s, %s, %s, 7, 20, 21, 1, 1, 1)",
            ["Здоровье", '{"ru": "Здоровье", "bs": "Zdravlje"}', "zdorovie"],
        )

        # Root: Недвижимость (id=11) - lft=23, rght=30
        cursor.execute(
            "INSERT INTO categories (name, name_i18n, slug, lft, rght, tree_id, level, is_active) "
            "VALUES (%s, %s, %s, 23, 30, 1, 0, 1)",
            ["Недвижимость", '{"ru": "Недвижимость", "bs": "Nekretnine"}', "nedvizhimost"],
        )
        cursor.execute(
            "INSERT INTO categories (name, name_i18n, slug, parent_id, lft, rght, tree_id, level, is_active) "
            "VALUES (%s, %s, %s, 11, 24, 25, 1, 1, 1)",
            ["Квартиры", '{"ru": "Квартиры", "bs": "Stanovi"}', "kvartiry"],
        )
        cursor.execute(
            "INSERT INTO categories (name, name_i18n, slug, parent_id, lft, rght, tree_id, level, is_active) "
            "VALUES (%s, %s, %s, 11, 26, 27, 1, 1, 1)",
            ["Дома", '{"ru": "Дома", "bs": "Kuće"}', "doma"],
        )
        cursor.execute(
            "INSERT INTO categories (name, name_i18n, slug, parent_id, lft, rght, tree_id, level, is_active) "
            "VALUES (%s, %s, %s, 11, 28, 29, 1, 1, 1)",
            ["Коммерция", '{"ru": "Коммерция", "bs": "Poslovni prostor"}', "kommercija"],
        )

        cursor.execute("PRAGMA foreign_keys = ON")


class Migration(migrations.Migration):
    dependencies = [
        ("categories", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_categories, migrations.RunPython.noop),
    ]