import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test')
django.setup()
from django.test.runner import DiscoverRunner
runner = DiscoverRunner(verbosity=0)
old_config = runner.setup_databases()
try:
    from django.contrib.auth import get_user_model
    from apps.locations.models import City
    from apps.categories.models import Category
    from apps.ads.models import Ad, AdStatus
    from apps.currencies.enums import CurrencyCode
    from django.test import Client
    User = get_user_model()
    seller = User.objects.create(username="s1", password="p")
    city = City.objects.create(country_code="ME", name="TC", region="C", slug="tc")
    category = Category.objects.create(name="Cat", slug="cat", is_active=True)
    Ad.objects.create(
        title="Test Ad", description="D", price_amount=100,
        price_currency=CurrencyCode.EUR.value, price_normalized_eur=100,
        category=category, city=city, category_name=category.name,
        status=AdStatus.PUBLISHED, source="telegram", user=seller,
        published_at=django.utils.timezone.now(),
    )
    client = Client()
    response = client.get("/search/?q=test&min_price=100", headers={"HX-Request": "true"})
    content = response.content.decode("utf-8")
    print("Status:", response.status_code)
    print("Has Clear all:", "Clear all filters" in content)
    print("Has Price chip:", "Price:" in content)
    print("Ctx active_price_min:", response.context.get("active_price_min"))
    print("Ctx query:", repr(response.context.get("query")))
    print("Ctx has_results:", response.context.get("has_results"))
    print("Ctx show_filters:", response.context.get("show_filters"))
    if "flex flex-wrap gap-2" in content:
        idx = content.index("flex flex-wrap gap-2")
        print("Chips section:", content[idx:idx+300])
    else:
        print("No chips container found")
finally:
    runner.teardown_databases(old_config)
