import json
import re
from collections import defaultdict, Counter

path = r'C:\py_dev\mko_bazuna\.action_logs\latest\trivy-results\trivy-image-results.sarif'
with open(path, 'r') as f:
    data = json.load(f)

run = data['runs'][0]
results = run.get('results', [])

# Parse message to extract package name, version, and fixed version
pkg_re = re.compile(r'Package:\s*(\S+)\nInstalled Version:\s*(\S+)\nVulnerability\s+(\S+)\nSeverity:\s*(\S+)\nFixed Version:\s*(\S*)')

by_pkg = defaultdict(lambda: {'count': 0, 'fixed': 0, 'unfixed': 0, 'levels': Counter()})
all_findings = []

for r in results:
    msg = r.get('message', {}).get('text', '')
    match = pkg_re.search(msg)
    if match:
        pkg = match.group(1)
        inst_ver = match.group(2)
        cve = match.group(3)
        sev = match.group(4)
        fixed_ver = match.group(5)
        
        level = r.get('level', 'none')
        
        all_findings.append({
            'pkg': pkg,
            'version': inst_ver,
            'cve': cve,
            'severity': sev,
            'level': level,
            'fixed_ver': fixed_ver,
            'has_fix': bool(fixed_ver),
        })
    
    # Get package name from location message
    loc_msg = ''
    locations = r.get('locations', [])
    if locations:
        loc_msg = locations[0].get('message', {}).get('text', '')

# Group by package
by_pkg = defaultdict(lambda: {'count': 0, 'fixed': 0, 'unfixed': 0, 'levels': Counter(), 'severities': Counter(), 'versions': set()})
for f in all_findings:
    p = by_pkg[f['pkg']]
    p['count'] += 1
    p['versions'].add(f['version'])
    p['severities'][f['severity']] += 1
    p['levels'][f['level']] += 1
    if f['has_fix']:
        p['fixed'] += 1
    else:
        p['unfixed'] += 1

# Sort by count descending
print(f"Total findings: {len(all_findings)}\n")

# Categorize packages
print("=== ALL PACKAGES (sorted by finding count) ===")
for pkg, info in sorted(by_pkg.items(), key=lambda x: -x[1]['count']):
    print(f"\n{pkg} (v{', '.join(info['versions'])})")
    print(f"  Total: {info['count']} | Fixed: {info['fixed']} | Unfixed: {info['unfixed']}")
    print(f"  By severity: {dict(info['severities'])}")
    print(f"  By SARIF level: {dict(info['levels'])}")
    # Show CVEs
    cves = [f['cve'] for f in all_findings if f['pkg'] == pkg]
    unique_cves = sorted(set(cves))
    print(f"  CVEs: {', '.join(unique_cves[:10])}")
    if len(unique_cves) > 10:
        print(f"  ... and {len(unique_cves) - 10} more")
