---
id: test-command-patterns
domain: commands
tags:
  - testing
  - docker
  - commands
related:
  - 13_test-env-acceleration_spec
---

# Test Command Patterns (canonical reference)

Grounded in committed configuration (`docker-compose.test.yml`, `Makefile`,
`Makefile.ps1`, `docker/entrypoint-test.sh`, `pyproject.toml`,
`.github/workflows/ci.yml`). Use these shapes so every test run is reproducible
and matches CI.

| Concern | Correct (canonical) | Incorrect / fragile (anti-pattern) |
|---|---|---|
| Project isolation | `make test` (Linux/macOS) or `.\Makefile.ps1 test` (Windows) set `COMPOSE_PROJECT_NAME=mko-bazuna-test` (Makefile line 22) | Manual `docker compose ... run test` without `-p mko-bazuna-test` → collides with `mko-bazuna-dev` volumes/networks. |
| Marker exclusion | `PYTEST_SKIP_MARKERS=seed` → entrypoint builds `-m "not (seed)"` | `PYTEST_OPTS="-m not seed"` directly (multi-token `-m` via `PYTEST_OPTS` is fragile: unquoted expansion). |
| DB cache vs fresh | `--reuse-db` by default; `make test-recreate` → `--no-reuse-db --create-db` after migration changes | `--reuse-db` against a drifted schema (~527 errors) — use `test-recreate` after migration changes. |
| Dev deps | The `test-runtime` image stage pre-installs the `[tool.uv]` dev group; `entrypoint-test.sh` runs `uv sync --frozen --no-install-project --group dev` (fast audit, ~1-2s) | Per-run cold `uv sync` install (25-29s) — the pre-compiled layer removes this tax. |
| Local xdist | `-n auto --dist loadgroup` is the default in `entrypoint-test.sh`, `Makefile` `test-recreate`, and `Makefile.ps1` `Invoke-TestRecreate`; `Invoke-Test` / `test-all` inherit it via the entrypoint default | Assuming serial local runs — local xdist parity with CI is achieved; CI already proves correctness. |
| One-shot lifecycle | `make up` for dev; `make build` recreates one-shots; `make seed` runs `run --rm` | `make up` after code-only changes expecting `migrate`/`seed` to re-run (they don't unless the image changed). |

## Equivalent direct invocation

`make test` (fast gate, skips the `seed` suite) is equivalent to:

```bash
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml \
  run --rm --env PYTEST_SKIP_MARKERS=seed test
```

which runs `entrypoint.sh` (wait_for_db + compile_messages) then `entrypoint-test.sh`
(`uv sync --group dev` + `uv run pytest -n auto --dist loadgroup -m "not (seed)" --reuse-db --tb=short`).

For a fresh schema after migration changes: `make test-recreate` →
`--no-reuse-db --create-db -n auto --dist loadgroup`.
