import urllib.request, urllib.parse, json
tests = ['iph','car','авт','аксессуар','ap','sof','tel','тран','вел']
out=[]
for q in tests:
    qs = urllib.parse.quote(q)
    try:
        r=urllib.request.urlopen('http://localhost:8000/api/search/autocomplete?q='+qs, timeout=10)
        data=json.loads(r.read().decode('utf-8'))
        sugs = [s['text'] for s in data.get('suggestions',[])]
        out.append(f"q='{q}' status={r.status} n={len(sugs)} -> {sugs}")
    except urllib.error.HTTPError as e:
        out.append(f"q='{q}' HTTP {e.code}")
    except Exception as e:
        out.append(f"q='{q}' ERROR {e}")
open('ac_diag.txt','w',encoding='utf-8').write('\n'.join(out))
print('\n'.join(out))
