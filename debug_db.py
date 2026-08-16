import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.db.models import Count, Func, F

from apps.categories.models import Category
from apps.ads.models import Ad
from apps.core.enums import AdStatus

# Case-insensitive duplicate category names
print("=== CASE-INSENSITIVE DUPLICATE CATEGORY NAMES ===")
from django.db.models.functions import Lower
groups = (
    Category.objects
    .annotate(lower_name=Lower("name"))
    .values("lower_name")
    .annotate(c=Count("id"))
    .filter(c__gt=1)
    .order_by("lower_name")
)
for g in groups:
    cats = list(Category.objects.filter(name__iexact=g["lower_name"]).values_list("id", "name", "slug", "parent_id"))
    print(f"  name='{g['lower_name']}' count={g['c']}: {cats}")

# FTS on known-in-title terms
from django.contrib.postgres.search import SearchQuery, SearchRank
for term in ["инструктор", "фитнес", "подгориц", "транспорт", "велосипед", "квартира", "телефон"]:
    sq = SearchQuery(term, search_type="websearch", config="russian")
    cnt = Ad.objects.filter(status=AdStatus.PUBLISHED).filter(search_vector=sq).count()
    print(f"FTS '{term}': {cnt} matches")

# Show category_name values that appear in ads + count per
print("=== published ads category_name histogram ===")
hist = Ad.objects.filter(status=AdStatus.PUBLISHED).values_list("category_name", flat=True)
from collections import Counter
for name, c in Counter(hist).most_common(15):
    print(f"  {name}: {c}")

# Total published
print("total published:", Ad.objects.filter(status=AdStatus.PUBLISHED).count())
print("published in transport subtree (desc of id 14):",
      Ad.objects.filter(status=AdStatus.PUBLISHED, category_id__in=Category.objects.get(id=14).get_descendants(include_self=True).values_list("id", flat=True)).count())
