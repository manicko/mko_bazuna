cities_content = open(r'src/backend/apps/locations/migrations/0002_seed_cities.py', 'r', encoding='utf-8').read()
lines = cities_content.split('\n')
city_lines = 0
for line in lines:
    if line.strip().startswith('(') and '"BA"' in line:
        city_lines += 1
print(f'Total city entries: {city_lines}')