# Python Semantic Map Builder

Indexes the Python source tree (`src/`) and emits JSON to
`.ai/structure/back/`.

## Run

```bash
uv run python .ai/builders/back/py_map.py
```

## Output

- `.ai/structure/back/py_map.json` — one entry per source file (path, module,
  layer, imports, classes, functions).
- `.ai/structure/back/py_anchors.json` — semantic anchors (function calls,
  return statements) with stable hashes.

## Notes

- Uses only the Python standard library (`ast`, `json`, `logging`). No PyYAML.
- Paths not under `src/`, ignored by `.gitignore`, or matching `IGNORE_DIRS`
  / `IGNORE_EXTENSIONS` in `.ai/builders/config.py` are excluded.
- Layer detection follows the precedence rules in `config.LAYER_PATTERNS`.
