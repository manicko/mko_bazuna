import subprocess, re

old = subprocess.check_output(
    ['git', '-C', '.', 'show', 'HEAD:src/theme/static/theme/css/output.css'],
    text=True,
)
new = open('src/theme/static/theme/css/output.css', encoding='utf-8').read()

print('old len', len(old), 'new len', len(new), 'delta', len(new) - len(old))


def selectors(s):
    # crude: find ".classname{" and ".cls\\:x{" selectors
    return set(re.findall(r'\.([A-Za-z0-9_\\-:.\[]+)\{', s))


so, sn = selectors(old), selectors(new)
print('old selectors', len(so), 'new selectors', len(sn))
print('REMOVED in new (regression!):', sorted(so - sn))
added = sorted(sn - so)
print('ADDED in new:', added)
