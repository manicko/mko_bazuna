import urllib.request, re

def check(qs):
    r = urllib.request.urlopen('http://localhost:8000/search/?q=' + qs)
    body = r.read().decode('utf-8','replace')
    no_res = 'No results found' in body or 'Ничего не найдено' in body
    ad_cards = len(re.findall(r'class="ad-card', body))
    # extract the visible "No results" or count
    m = re.findall(r'No results found for &quot;([^&]*)&quot;|Ничего не найдено', body)
    return f"status={r.status} no_results={no_res} ad_cards={ad_cards} msg={m[:1]}"

tests = {
    'electronics': '%D1%8D%D0%BB%D0%B5%D0%BA%D1%82%D1%80%D0%BE%D0%BD%D0%B8%D0%BA%D0%B0',  # электроника
    'auto': '%D0%B0%D0%B2%D1%82%D0%BE%D0%BC%D0%BE%D0%B1%D0%B8%D0%BB%D0%B8',  # автомобили
    'instructor': '%D0%B8%D0%BD%D1%81%D1%82%D1%80%D1%83%D0%BA%D1%82%D0%BE%D1%80',  # инструктор
    'transport': '%D1%82%D1%80%D0%B0%D0%BD%D1%81%D0%BF%D0%BE%D1%80%D1%82',  # транспорт
    'bicycle': '%D0%B2%D0%B5%D0%BB%D0%BE%D1%81%D0%B8%D0%BF%D0%B5%D0%B0%D0%B4',  # велосипед (will 500)
    'food_ru': '%D0%BF%D0%B8%D1%89%D0%B5',  # пище/food(ru) - may be empty
    'phones': '%D1%82%D0%B5%D0%BB%D0%B5%D1%84%D0%BE%D0%BD%D1%8B',  # телефоны
}
out=[]
for name, qs in tests.items():
    try:
        out.append(f"{name}: {check(qs)}")
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8','replace')
        msg = re.findall(r'Exception Value.*?<pre>(.*?)</pre>', body, re.S)
        out.append(f"{name}: HTTP {e.code} | {msg[0].strip()[:120] if msg else ''}")
    except Exception as e:
        out.append(f"{name}: ERROR {e}")
open('search_view_diag.txt','w',encoding='utf-8').write('\n'.join(out))
print('\n'.join(out))
