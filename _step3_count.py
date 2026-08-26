#!/usr/bin/env python3
"""Count test results from Step 3 measurement output files."""
import os

backend = "/app/src/backend"
files = {
    "_step3_fg.txt": "Fast-gate",
    "_step3_seed.txt": "Seed",
    "_step3_unit.txt": "Unit serial",
    "_step3_conc.txt": "Concurrent",
    "_step3_sett.txt": "Settings",
}

for fname, label in files.items():
    path = os.path.join(backend, fname)
    if not os.path.exists(path):
        print(f"\n[{label}] {fname}: NOT FOUND")
        continue
    with open(path, "r", errors="replace") as f:
        lines = f.readlines()
    print(f"\n[{label}] {fname} ({len(lines)} lines)")
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Look for progress lines: contain at least one . or F or E, and no spaces between chars
        # Progress lines in pytest -q look like dots/f/E/us with no spaces
        if len(stripped) > 0:
            # Check if this is a progress line (all chars are . F E s u etc.)
            allowed = set(".FEsu\n\r ")
            if set(stripped) <= allowed and len(stripped) > 3:
                dots = stripped.count(".")
                fs = stripped.count("F")
                es = stripped.count("E")
                us = stripped.count("u")
                ss = stripped.count("s")
                total = dots + fs + es + us + ss
                print(f"  Line {i+1}: progress line")
                print(f"  Dots(pass)={dots}  F(fail)={fs}  E(error)={es}  u={us}  s(skip)={ss}")
                print(f"  Total chars: {total}")
    # Look for EXIT line
    for i, line in enumerate(lines):
        if line.strip().startswith("EXIT="):
            print(f"  EXIT: {line.strip()}")
    # Look for summary line (e.g., "3 passed, 1041 deselected in 26.96s")
    for i, line in enumerate(lines):
        s = line.strip()
        if "passed" in s and ("in" in s and "s" in s):
            print(f"  Summary: {s}")
