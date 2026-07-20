import re

# Count categories
cat_content = open(r'src/backend/apps/categories/migrations/0002_seed_categories.py', 'r', encoding='utf-8').read()
# Find all INSERT INTO lines (handle both single-line and multi-line)
inserts = cat_content.count('cursor.execute(')
print(f'Category cursor.execute calls: {inserts}')

# Count cities - look for actual tuple entries
city_content = open(r'src/backend/apps/locations/migrations/0002_seed_cities.py', 'r', encoding='utf-8').read()
city_entries = [line for line in city_content.split('\n') if '("sarajevo' in line or '("mostar' in line or ',"zenica' in line or ',"bihac' in line or ',"tuzla' in line]
print(f'Lines with city slugs: {len(city_entries)}')

# Better approach - just count parenthesized tuples with 5 elements
city_tuples = city_content.count('("sarajevo') + city_content.count('("mostar')
print(f'City tuples (sarajevo/mostar check): at least {city_tuples}')