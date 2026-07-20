# TypeScript Semantic Map Builder

Optional extractor for projects that ship a TypeScript/React frontend. Mko
Bazuna uses Django templates only (HTMX MPA), so this builder is **gated off**
by default (`ENABLE_TS=False` in `.ai/builders/config.py`).

## Enable (for TS projects)

Set the enable flag and run with plain Node.js — no `ts-morph`, no `js-yaml`,
no `ts-node`, no `tsconfig` required:

```bash
# Node 22+ (strips types natively)
ENABLE_TS=true node --experimental-strip-types .ai/builders/front/ts_map.ts

# Or rename to .js and run directly
cp .ai/builders/front/ts_map.ts ts_map.js
ENABLE_TS=true node ts_map.js
```

## Configuration (env vars)

- `ENABLE_TS` — `true` to run the scan (default `false`).
- `TS_SRC_ROOT` — directory to scan (default `frontend/`).
- `TS_OUTPUT` — output directory (default `.ai/structure/front`).

## Output

- `.ai/structure/front/ts_map.json` — one entry per source file (components,
  hooks, JSX tags, layer).
- `.ai/structure/front/ts_anchors.json` — component/hook anchors.

## Portability

The module is dependency-free (Node.js stdlib only: `fs`, `path`, `crypto`).
Copy `ts_map.ts` into any project, point `TS_SRC_ROOT` at the sources, and run.
