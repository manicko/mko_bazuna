# Seed migration for Montenegro cities

from django.db import migrations


def create_cities(apps, schema_editor):
    """Create seed cities for Montenegro."""
    City = apps.get_model("locations", "City")

    cities = [
        # Montenegro — all 23 official municipalities
        ("podgorica", "Подгорица", "ME", "Montenegro", {"ru": "Подгорица", "bs": "Podgorica"}),
        ("niksic", "Никшич", "ME", "Montenegro", {"ru": "Никшич", "bs": "Nikšić"}),
        ("kotor", "Котор", "ME", "Montenegro", {"ru": "Котор", "bs": "Kotor"}),
        ("herceg_novi", "Херцег-Нови", "ME", "Montenegro", {"ru": "Херцег-Нови", "bs": "Herceg Novi"}),
        ("cetinje", "Цетиње", "ME", "Montenegro", {"ru": "Цетиње", "bs": "Cetinje"}),
        ("rozaje", "Рожаје", "ME", "Montenegro", {"ru": "Рожаје", "bs": "Rožaje"}),
        ("ulcinj", "Улцињ", "ME", "Montenegro", {"ru": "Улцињ", "bs": "Ulcinj"}),
        ("bar", "Бар", "ME", "Montenegro", {"ru": "Бар", "bs": "Bar"}),
        ("budva", "Будва", "ME", "Montenegro", {"ru": "Будва", "bs": "Budva"}),
        ("tivat", "Тиват", "ME", "Montenegro", {"ru": "Тиват", "bs": "Tivat"}),
        ("zeta", "Зета", "ME", "Montenegro", {"ru": "Зета", "bs": "Zeta"}),
        ("mojkovac", "Мојковац", "ME", "Montenegro", {"ru": "Мојковац", "bs": "Mojkovac"}),
        ("zabljak", "Жабљак", "ME", "Montenegro", {"ru": "Жабљак", "bs": "Žabljak"}),
        ("plav", "Плав", "ME", "Montenegro", {"ru": "Плав", "bs": "Plav"}),
        ("gusinje", "Гусиње", "ME", "Montenegro", {"ru": "Гусиње", "bs": "Gusinje"}),
        ("pljevlja", "Пљевља", "ME", "Montenegro", {"ru": "Пљевља", "bs": "Pljevlja"}),
        ("savnik", "Шавник", "ME", "Montenegro", {"ru": "Шавник", "bs": "Šavnik"}),
        ("andrijevica", "Андријевица", "ME", "Montenegro", {"ru": "Андријевица", "bs": "Andrijevica"}),
        ("berane", "Беране", "ME", "Montenegro", {"ru": "Беране", "bs": "Berane"}),
        ("bijelo_polje", "Бијело Поље", "ME", "Montenegro", {"ru": "Бијело Поље", "bs": "Bijelo Polje"}),
        ("danilovgrad", "Даниловград", "ME", "Montenegro", {"ru": "Даниловград", "bs": "Danilovgrad"}),
        ("petrovac", "Петровац", "ME", "Montenegro", {"ru": "Петровац", "bs": "Petrovac"}),
        ("tuzi", "Тузи", "ME", "Montenegro", {"ru": "Тузи", "bs": "Tuzi"}),
    ]

    for slug, name, country_code, region, name_i18n in cities:
        City.objects.create(
            slug=slug,
            name=name,
            country_code=country_code,
            region=region,
            name_i18n=name_i18n,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_cities, migrations.RunPython.noop),
    ]