"""Seed migration for categories — creates initial category tree using ORM.

Replaces previous raw-SQL approach with Django ORM + MPTT for proper
tree structure management.
"""

import json

from django.db import migrations


def create_categories(apps, schema_editor):
    """Create seed categories with proper MPTT tree structure using Django ORM.

    Creates 14 categories: 3 roots + 5 + 4 + 3 children.
    MPTT computes lft/rght automatically on save().
    """
    Category = apps.get_model("categories", "Category")

    # Root: Товары (products)
    tovary = Category.objects.create(
        name="Товары",
        name_i18n=json.dumps({"ru": "Товары", "bs": "Proizvodi"}),
        slug="tovary",
        is_active=True,
    )

    # Children of Товары
    Category.objects.create(
        name="Электроника",
        name_i18n=json.dumps({"ru": "Электроника", "bs": "Elektronika"}),
        slug="elektronika",
        parent=tovary,
        is_active=True,
    )
    Category.objects.create(
        name="Одежда",
        name_i18n=json.dumps({"ru": "Одежда", "bs": "Odeća"}),
        slug="odezhda",
        parent=tovary,
        is_active=True,
    )
    Category.objects.create(
        name="Дом и сад",
        name_i18n=json.dumps({"ru": "Дом и сад", "bs": "Kuća i bašta"}),
        slug="dom",
        parent=tovary,
        is_active=True,
    )
    Category.objects.create(
        name="Авто товары",
        name_i18n=json.dumps({"ru": "Авто товары", "bs": "Proizvodi za automobile"}),
        slug="avto",
        parent=tovary,
        is_active=True,
    )
    Category.objects.create(
        name="Спорт",
        name_i18n=json.dumps({"ru": "Спорт", "bs": "Sport"}),
        slug="sport",
        parent=tovary,
        is_active=True,
    )

    # Root: Услуги (services)
    uslugi = Category.objects.create(
        name="Услуги",
        name_i18n=json.dumps({"ru": "Услуги", "bs": "Usluge"}),
        slug="uslugi",
        is_active=True,
    )

    # Children of Услуги
    Category.objects.create(
        name="Ремонт",
        name_i18n=json.dumps({"ru": "Ремонт", "bs": "Popravka"}),
        slug="remont",
        parent=uslugi,
        is_active=True,
    )
    Category.objects.create(
        name="Перевозки",
        name_i18n=json.dumps({"ru": "Перевозки", "bs": "Prevoz"}),
        slug="perevozki",
        parent=uslugi,
        is_active=True,
    )
    Category.objects.create(
        name="Образование",
        name_i18n=json.dumps({"ru": "Образование", "bs": "Obrazovanje"}),
        slug="obrazovanie",
        parent=uslugi,
        is_active=True,
    )
    Category.objects.create(
        name="Здоровье",
        name_i18n=json.dumps({"ru": "Здоровье", "bs": "Zdravlje"}),
        slug="zdorovie",
        parent=uslugi,
        is_active=True,
    )

    # Root: Недвижимость (real estate)
    nedvizhimost = Category.objects.create(
        name="Недвижимость",
        name_i18n=json.dumps({"ru": "Недвижимость", "bs": "Nekretnine"}),
        slug="nedvizhimost",
        is_active=True,
    )

    # Children of Недвижимость
    Category.objects.create(
        name="Квартиры",
        name_i18n=json.dumps({"ru": "Квартиры", "bs": "Stanovi"}),
        slug="kvartiry",
        parent=nedvizhimost,
        is_active=True,
    )
    Category.objects.create(
        name="Дома",
        name_i18n=json.dumps({"ru": "Дома", "bs": "Kuće"}),
        slug="doma",
        parent=nedvizhimost,
        is_active=True,
    )
    Category.objects.create(
        name="Коммерция",
        name_i18n=json.dumps({"ru": "Коммерция", "bs": "Poslovni prostor"}),
        slug="kommercija",
        parent=nedvizhimost,
        is_active=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("categories", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_categories, migrations.RunPython.noop),
    ]