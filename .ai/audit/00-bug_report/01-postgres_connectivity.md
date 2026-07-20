# Bug Report: Test Database Connectivity

## ID: 01

## Summary
Test execution hangs when attempting to connect to PostgreSQL database. Tests cannot be validated via `uv run pytest` from the host machine.

## Environment
- Docker PostgreSQL container: `postgres:18-alpine` (running as `docker-db-1`)
- Host: Windows 11
- Django settings: `config.settings.test`
- Database URL: `postgres://postgres@localhost:5432/mko_bazuna`

## Symptoms
- `uv run pytest` commands timeout without output
- PostgreSQL accepts connections internally (tested via `docker exec`)
- Host port 5432 is mapped but connections hang on Windows

## Investigation
- The database `mko_bazuna` exists in the container
- No tables exist (migrations not applied)
- Docker network: `172.21.0.4` for postgres
- Port mapping: `127.0.0.1:5432->5432/tcp`

## Impact
Cannot run `uv run pytest <path>` locally to validate test changes. Tests must be run via Docker compose test service.

## Recommendation
Fix PostgreSQL port mapping on Windows or run tests via `docker-compose -f docker-compose.test.yml run test`.