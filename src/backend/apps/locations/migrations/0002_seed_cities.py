# Seed migration for Bosnia and Herzegovina cities

from django.db import migrations


def create_cities(apps, schema_editor):
    """Create seed cities for Bosnia and Herzegovina."""
    City = apps.get_model("locations", "City")

    cities = [
        # Federation of Bosnia and Herzegovina
        ("sarajevo", "Сараево", "BA", "FBiH", {"ru": "Сараево", "bs": "Sarajevo"}),
        ("mostar", "Мостар", "BA", "FBiH", {"ru": "Мостар", "bs": "Mostar"}),
        ("zenica", "Зеница", "BA", "FBiH", {"ru": "Зеница", "bs": "Zenica"}),
        ("bihac", "Бихаћ", "BA", "FBiH", {"ru": "Бихаћ", "bs": "Bihać"}),
        ("tuzla", "Тузла", "BA", "FBiH", {"ru": "Тузла", "bs": "Tuzla"}),
        ("livno", "Ливно", "BA", "FBiH", {"ru": "Ливно", "bs": "Livno"}),
        ("zivinice", "Зивинице", "BA", "FBiH", {"ru": "Зивинице", "bs": "Živinice"}),
        ("klopce", "Клопце", "BA", "FBiH", {"ru": "Клопце", "bs": "Klopče"}),
        ("derventa", "Дервента", "BA", "FBiH", {"ru": "Дервента", "bs": "Derventa"}),
        ("goražde", "Горажде", "BA", "FBiH", {"ru": "Горажде", "bs": "Goražde"}),
        # Republic of Srpska
        ("banja_luka", "Баня-Лука", "BA", "RS", {"ru": "Баня-Лука", "bs": "Banja Luka"}),
        ("prijedor", "Прийедор", "BA", "RS", {"ru": "Прийедор", "bs": "Prijedor"}),
        ("doboj", "Добой", "BA", "RS", {"ru": "Добой", "bs": "Doboj"}),
        ("pale", "Пале", "BA", "RS", {"ru": "Пале", "bs": "Pale"}),
        ("foca", "Фоца", "BA", "RS", {"ru": "Фоца", "bs": "Foča"}),
        ("trebinje", "Требинье", "BA", "RS", {"ru": "Требинье", "bs": "Trebinje"}),
        ("jajce", "Яйце", "BA", "RS", {"ru": "Яйце", "bs": "Jajce"}),
        ("mrkonjic_grad", "Мрконьиц", "BA", "RS", {"ru": "Мрконьиц", "bs": "Mrkonjić Grad"}),
        ("bijeljina", "Бијељина", "BA", "RS", {"ru": "Бијељина", "bs": "Bijeljina"}),
        ("zepce", "Зепце", "BA", "RS", {"ru": "Зепце", "bs": "Žepče"}),
        ("stanari", "Станари", "BA", "RS", {"ru": "Станари", "bs": "Stanari"}),
        ("ljubinje", "Любинье", "BA", "RS", {"ru": "Любинье", "bs": "Ljubinje"}),
        ("rogatica", "Рогатска", "BA", "RS", {"ru": "Рогатска", "bs": "Rogatica"}),
        ("drina", "Дрина", "BA", "RS", {"ru": "Дрина", "bs": "Drina"}),
        ("bosanska_kravica", "Босанска Кравица", "BA", "RS", {"ru": "Босанска Кравица", "bs": "Bosanska Kravica"}),
        ("bosanski_novi", "Босански Нови", "BA", "RS", {"ru": "Босански Нови", "bs": "Bosanski Novi"}),
        ("bosanski_samac", "Босански Самац", "BA", "RS", {"ru": "Босански Самац", "bs": "Bosanski Samac"}),
        ("celic", "Челић", "BA", "RS", {"ru": "Челић", "bs": "Čelić"}),
        ("han_pijesak", "Хан Пијесак", "BA", "RS", {"ru": "Хан Пијесак", "bs": "Han Pijesak"}),
        ("janja", "Янња", "BA", "RS", {"ru": "Янња", "bs": "Janja"}),
        ("kalinovik", "Калиновык", "BA", "RS", {"ru": "Калиновык", "bs": "Kalinovik"}),
        ("kovilje", "Ковиље", "BA", "RS", {"ru": "Ковиље", "bs": "Kovilje"}),
        ("kotor_varos", "Котор Варош", "BA", "RS", {"ru": "Котор Варош", "bs": "Kotor Varoš"}),
        ("krupanj", "Крупян", "BA", "RS", {"ru": "Крупян", "bs": "Krupanj"}),
        ("mahovica", "Маховица", "BA", "RS", {"ru": "Маховица", "bs": "Mahovica"}),
        ("milici", "Милићи", "BA", "RS", {"ru": "Милићи", "bs": "Milići"}),
        ("odzak", "Оџак", "BA", "RS", {"ru": "Оџак", "bs": "Odžak"}),
        ("petrovo", "Петрово", "BA", "RS", {"ru": "Петрово", "bs": "Petrovo"}),
        ("raca", "Раче", "BA", "RS", {"ru": "Раче", "bs": "Rača"}),
        ("srebrenica", "Сребница", "BA", "RS", {"ru": "Сребница", "bs": "Srebrenica"}),
        ("tocak", "Точак", "BA", "RS", {"ru": "Точак", "bs": "Točak"}),
        ("vratarica", "Вратарица", "BA", "RS", {"ru": "Вратарица", "bs": "Vratarica"}),
        ("vlasenica", "Власеница", "BA", "RS", {"ru": "Власеница", "bs": "Vlasenica"}),
        ("gacko", "Гако", "BA", "RS", {"ru": "Гако", "bs": "Gacko"}),
        ("kosan", "Косан", "BA", "RS", {"ru": "Косан", "bs": "Kosan"}),
        ("višegrad", "Вишеград", "BA", "RS", {"ru": "Вишеград", "bs": "Višegrad"}),
        # Brčko District
        ("brcko", "Брчко", "BA", "Brčko", {"ru": "Брчко", "bs": "Brčko"}),
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