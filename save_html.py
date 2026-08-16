import urllib.request, urllib.parse
for name, q in [('electronics','%D1%8D%D0%BB%D0%B5%D0%BA%D1%82%D1%80%D0%BE%D0%BD%D0%B8%D0%BA%D0%B0'),
               ('instructor','%D0%B8%D0%BD%D1%81%D1%82%D1%80%D1%83%D0%BA%D1%82%D0%BE%D1%80'),
               ('transport','%D1%82%D1%80%D0%B0%D0%BD%D1%81%D0%BF%D0%BE%D1%80%D1%82')]:
    try:
        r=urllib.request.urlopen('http://localhost:8000/search/?q='+q)
        open(f'C:/py_dev/mko_bazuna/{name}.html','wb').write(r.read())
    except urllib.error.HTTPError as e:
        open(f'C:/py_dev/mko_bazuna/{name}.html','wb').write(e.read())
print('done')
