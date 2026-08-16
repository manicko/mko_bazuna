import urllib.request, re

# Capture the 500 traceback HTML for 'велосипед'
url = 'http://localhost:8000/search/?q=%D0%B2%D0%B5%D0%BB%D0%BE%D1%81%D0%B8%D0%BF%D0%B5%D0%B4'
try:
    r = urllib.request.urlopen(url)
    body = r.read().decode('utf-8','replace')
    open('C:/py_dev/mko_bazuna/err_500.html','w',encoding='utf-8').write(body[:8000])
    print('status', r.status)
except urllib.error.HTTPError as e:
    body = e.read().decode('utf-8','replace')
    open('C:/py_dev/mko_bazuna/err_500.html','w',encoding='utf-8').write(body[:12000])
    print('HTTPError status', e.code)
print('saved err_500.html')
