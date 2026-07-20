# Semantic Map Builders

Tooling that scans the codebase and produces machine-readable "semantic maps"
(files + anchors) used by downstream docs/agents. All configuration lives in
[`config.py`](./config.py).

## Layout

```
.ai/builders/
├── config.py          # Shared paths, ignore sets, layer patterns, ENABLE_TS
├── back/
│   ├── py_map.py       # Python AST indexer (stdlib only, JSON output)
│   └── run.md
└── front/
    ├── ts_map.ts       # TS/React regex extractor (Node stdlib only, JSON)
    └── run.md
```

## Python builder (`back/py_map.py`)

Indexes `src/` with the `ast` module and writes two JSON files to
`.ai/structure/back/`:

- `py_map.json` — per-file: `path`, `module`, `layer`, `imports`, `classes`,
  `functions`.
- `py_anchors.json` — semantic anchors (`function_call`, `return_statement`)
  with stable md5 hashes.

Run:

```bash
uv run python .ai/builders/back/py_map.py
```

Facts:

- **No third-party deps** — uses `ast`, `json`, `logging` only (PyYAML removed).
- **Git-aware** — honors `.gitignore` via `git check-ignore`; falls back to a
  hardcoded ignore set when git is unavailable.
- **Extension filtering** — `.pyc/.pyo/.pyd/.md` skipped via `IGNORE_EXTENSIONS`.
- **Layer detection** — `api > handler > state > filter > service > model >
  config > other`, as listed in `LAYER_PATTERNS`.

## TypeScript builder (`front/ts_map.ts`)

Optional. Gated by `ENABLE_TS=False` for Mko Bazuna (no frontend here).

- Dependency-free: only Node.js built-ins (`fs`, `path`, `crypto`). No
  `ts-morph`, `js-yaml`, or `tsconfig`.
- Regex/string extraction of components, hooks, and JSX tags; JSON output.
- Configurable via `ENABLE_TS`, `TS_SRC_ROOT`, `TS_OUTPUT` env vars.

See [`front/run.md`](./front/run.md) for run instructions.

## Output format

`py_map.json` entry:

```json
{
  "path": "src/backend/apps/ads/models.py",
  "module": "backend.apps.ads.models",
  "layer": "model",
  "imports": ["django.db.models"],
  "classes": ["Ad", "AdImage"],
  "functions": ["__str__", "generate_storage_key"]
}
```

`py_anchors.json` entry:

```json
{
  "id": "abc12345",
  "symbol_path": ["Ad", "save"],
  "type": "function_call",
  "value": "full_clean",
  "stable_hash": "abc12345",
  "file": "src/backend/apps/ads/models.py"
}
```
