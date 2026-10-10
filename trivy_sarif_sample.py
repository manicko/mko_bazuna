import json
from collections import defaultdict

path = r'C:\py_dev\mko_bazuna\.action_logs\latest\trivy-results\trivy-image-results.sarif'
with open(path, 'r') as f:
    data = json.load(f)

run = data['runs'][0]
results = run.get('results', [])

# Look at a sample result to understand the structure
print("=== Sample result (first ERROR level) ===")
for r in results:
    if r.get('level') == 'error':
        # Print the full structure
        print(json.dumps(r, indent=2)[:3000])
        break

print("\n\n=== Sample result (first result) ===")
print(json.dumps(results[0], indent=2)[:3000])
