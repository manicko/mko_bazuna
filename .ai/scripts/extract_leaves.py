import yaml, json

CATALOG = r'C:\py_dev\mko_bazuna\src/backend/apps/categories/catalog/categories.yaml'

with open(CATALOG, encoding='utf-8') as f:
    data = yaml.safe_load(f)

SECTIONS = ['real-estate', 'transport', 'goods', 'animals', 'services-jobs', 'business', 'charity']

groups = {}
total = 0
for cat in data['categories']:
    section = cat['slug']
    leaves = []
    stack = [cat]
    while stack:
        c = stack.pop(0)
        kids = c.get('children')
        if kids:
            stack.extend(kids)
        else:
            leaves.append(c)
    groups[section] = leaves
    total += len(leaves)

for s in SECTIONS:
    print(f'=== {s} ({len(groups[s])} leaves) ===')
    for leaf in groups[s]:
        ru = leaf.get('name_i18n',{}).get('ru', leaf.get('name',''))
        en = leaf.get('name_i18n',{}).get('en', leaf.get('name',''))
        bs = leaf.get('name_i18n',{}).get('bs', leaf.get('name',''))
        print(f'  {leaf["slug"]}|{ru}|{en}|{bs}')

print(f'\nTOTAL: {total}')
