import re, sys

with open(sys.argv[1], "r", encoding="utf-8") as f:
    html = f.read()

# Output to file to avoid encoding issues
with open("/tmp/chip_analysis.txt", "w", encoding="utf-8") as out:
    # Find chip section
    chips_start = html.find("Active filter chips")
    if chips_start > -1:
        chunk = html[chips_start : chips_start + 3000]
        out.write("=== CHIP SECTION ===\n")
        out.write(chunk[:2000])
        out.write("\n\n")
        # Extract all href values from chip links
        hrefs = re.findall(r'href="([^"]*)"', chunk)
        out.write("=== CHIP HREFS ===\n")
        for h in hrefs:
            out.write(h + "\n")
        out.write("\n\n")

    # Find clear all link
    clear_idx = html.find("Очистить")
    if clear_idx > -1:
        out.write("=== CLEAR ALL CONTEXT ===\n")
        out.write(html[clear_idx - 300 : clear_idx + 300])
        out.write("\n\n")

    # Find hidden category input
    cat_inputs = re.findall(r'<input[^>]*name="category"[^>]*>', html)
    out.write("=== HIDDEN CATEGORY INPUTS ===\n")
    for ci in cat_inputs:
        out.write(ci + "\n")

    # Find the filter form to check hx-get
    form_hx = re.findall(r'hx-get="([^"]*)"', html)
    out.write("\n=== HX-GET VALUES ===\n")
    for hx in form_hx:
        out.write(hx + "\n")

    # Find sort select
    sort_idx = html.find('name="sort"')
    if sort_idx > -1:
        out.write("\n=== SORT SELECT ===\n")
        out.write(html[sort_idx - 100 : sort_idx + 300])

    # Check pagination
    pagination = re.findall(r"page=\d+", html)
    out.write("\n\n=== PAGINATION ===\n")
    for p in pagination[:10]:
        out.write(p + "\n")
