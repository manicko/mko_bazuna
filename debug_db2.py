import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from apps.search.models import PopularSearch, SearchHistory
from apps.categories.models import Category
from apps.locations.models import City

print("=== PopularSearch records ===")
recs = list(PopularSearch.objects.all().order_by("-hit_count")[:20].values("query", "query_normalized", "hit_count"))
print("total PopularSearch:", PopularSearch.objects.count())
for r in recs:
    print(f"  q={r['query']!r} norm={r['query_normalized']!r} hits={r['hit_count']}")

print("\n=== SearchHistory records ===")
print("total:", SearchHistory.objects.count())

print("\n=== PopularSearch with hit_count>=10 ===")
pop10 = list(PopularSearch.objects.filter(hit_count__gte=10).values_list("query", flat=True))
print("count>=10:", len(pop10))
print(pop10[:20])
