import re
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

html_path = r"C:\Users\Om\.local\share\kilo\tool-output\tool_fbca44304001wOvk0mud907Q7M"
with open(html_path, encoding="utf-8") as f:
    html = f.read()

# Find __preloadedState__
ps_start = html.find('__preloadedState__ = "')
if ps_start == -1:
    print("ERROR: Could not find __preloadedState__")
    sys.exit(1)

ps_start += len('__preloadedState__ = "')
# Find the matching end quote (the JSON string might contain escaped quotes)
# The JSON string ends with a newline followed by </script>
ps_end = html.find("\n", ps_start)
if ps_end == -1:
    ps_end = ps_start + 500000

ps_raw = html[ps_start:ps_end].strip()
# Remove trailing quote and any trailing characters
if ps_raw.endswith('"'):
    ps_raw = ps_raw[:-1]

# Unescape the JSON string
ps_decoded = ps_raw.encode('utf-8').decode('unicode_escape')
# The result might still have escaped quotes
ps_decoded = ps_decoded.replace('\\"', '"')

print(f"Decoded preloaded state length: {len(ps_decoded)}")

# Find categoryTree in the decoded state
ct_idx = ps_decoded.find('"categoryTree"')
if ct_idx == -1:
    print("ERROR: categoryTree not found in preloaded state")
    # Try finding it case-insensitively
    ct_idx = ps_decoded.lower().find("categorytree")
    print(f"categorytree (case-insensitive) at: {ct_idx}")
    if ct_idx > 0:
        snippet = ps_decoded[ct_idx-100:ct_idx+500]
        print(f"Context: {snippet}")
else:
    print(f"categoryTree found at index {ct_idx}")
    snippet = ps_decoded[ct_idx:ct_idx+500]
    print(f"Context: {snippet}")

# Try to find the "Услуги" tree structure using the context we know
# From the earlier search, we know the structure starts like:
# "categoryTree":[{"categoryId":114,"id":26486,"name":"Услуги","subs":[...
uslugi_idx = ps_decoded.find('"id":26486,"name":"Услуги"')
if uslugi_idx == -1:
    # Try with decoded unicode
    uslugi_idx = ps_decoded.find('"id":26486,"name":"Услуги"')
    if uslugi_idx == -1:
        # Try without the name check
        uslugi_idx = ps_decoded.find('"id":26486')
print(f"\nУслуги node found at index: {uslugi_idx}")
if uslugi_idx > 0:
    snippet = ps_decoded[uslugi_idx-50:uslugi_idx+2000]
    print(f"Context: {snippet[:2000]}")
