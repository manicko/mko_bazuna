import urllib.request, urllib.parse, re, os

QUERIES = ['food', '%D0%B2%D0%B5%D0%BB%D0%BE%D1%81%D0%B8%D0%BF%D0%B5%D0%B4',  # велосипед
           '%D0%BA%D0%B2%D0%B0%D1%80%D1%82%D0%B8%D0%BD%D0%B0',  # квартирина
           '%D1%82%D1%80%D0%B0%D0%BD%D1%81%D0%BF%D0%BE%D1%80%D1%82',  # транспорт
           '%D1%82%D0%B5%D0%BB%D0%B5%D1%84%D0%BE%D0%BD']  # телефон

def check(qurl, label):
    try:
        r = urllib.request.urlopen(qurl)
        body = r.read().decode('utf-8', 'replace')
    except Exception as ex:
        print(f"{label}: ERROR {ex}")
        return
    no_res = 'No results found' in body or 'Ничего не найдено' in body
    ad_cards = len(re.findall(r'class="ad-card', body))
    title_match = re.findall(r'<title>([^<]*)</title>', body)
    print(f"{label}: status={r.status} no_results_msg={no_res} ad_cards={ad_cards} title={title_match[:1]}")

for q in QUERIES:
    check('http://localhost:8000/search/?q=' + q, 'search')

# Also test the autocomplete API
for q in ['%D1%82%D1%80%D0%B0%D0%BD', '%D0%B2%D0%B5%D0%BB', 'foo']:
    try:
        r = urllib.request.urlopen('http://localhost:8000/api/search/autocomplete?q=' + q)
        body = r.read().decode('utf-8', 'replace')
        print(f"autocomplete q={q}: status={r.status} body={body[:200]}")
    except Exception as ex:
        print(f"autocomplete q={q}: ERROR {ex}")
