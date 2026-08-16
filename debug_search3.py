import urllib.request, re

def check(qurl):
    r = urllib.request.urlopen(qurl)
    body = r.read().decode('utf-8', 'replace')
    no_res = 'No results found' in body or 'Ничего не найдено' in body
    ad_cards = len(re.findall(r'class="ad-card', body))
    title = re.findall(r'<title>([^<]*)</title>', body)
    return f"status={r.status} no_results={no_res} ad_cards={ad_cards} title={title[:1]}"

# Russian queries that should match content
queries = {
    'food': 'http://localhost:8000/search/?q=food',
    'velosiped': 'http://localhost:8000/search/?q=%D0%B2%D0%B5%D0%BB%D0%BE%D1%81%D0%B8%D0%BF%D0%B5%D0%B4',
    'kvartira': 'http://localhost:8000/search/?q=%D0%BA%D0%B2%D0%B0%D1%80%D1%82%D0%B8%D1%80%D0%B0',
    'transport': 'http://localhost:8000/search/?q=%D1%82%D1%80%D0%B0%D0%BD%D1%81%D0%BF%D0%BE%D1%80%D1%82',
    'telefon': 'http://localhost:8000/search/?q=%D1%82%D0%B5%D0%BB%D0%B5%D1%84%D0%BE%D0%BD',
    'telegramma': 'http://localhost:8000/search/?q=%D1%82%D0%B5%D0%BB%D0%B5%D0%B3%D1%80%D0%B0%D0%BC%D0%BC%D0%B0',
}
out = []
for name, url in queries.items():
    try:
        out.append(f"{name}: {check(url)}")
    except Exception as ex:
        out.append(f"{name}: ERROR {ex}")

# autocomplete API tests
ac = {
    'transport': 'http://localhost:8000/api/search/autocomplete?q=%D1%82%D1%80%D0%B0%D0%BD',
    'velosiped': 'http://localhost:8000/api/search/autocomplete?q=%D0%B2%D0%B5%D0%BB',
    'food': 'http://localhost:8000/api/search/autocomplete?q=food',
}
for name, url in ac.items():
    try:
        r = urllib.request.urlopen(url)
        body = r.read().decode('utf-8','replace')
        out.append(f"ac[{name}]: status={r.status} body={body[:300]}")
    except Exception as ex:
        out.append(f"ac[{name}]: ERROR {ex}")

open('C:/py_dev/mko_bazuna/search_diag.txt','w',encoding='utf-8').write('\n'.join(out))
print('\n'.join(out))
