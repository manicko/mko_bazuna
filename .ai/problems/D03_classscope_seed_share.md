---
id: d03_transactiontestcase_classscope_sharing
title: D-03 class-scoped seed sharing impossible under pytest-django truncation
source: .ai/plans/done/27_test-optimization-and-verification_plan_DONE.md
status: open
severity: low
---

# Problem: Class-scoped seed data sharing fails under pytest-django TransactionTestCase

## Description

Plan 27 tasks D-03 proposed replacing 5 per-test `call_command("seed")` runs in
`TestSeedFilterCoverage` (seed/tests/test_seed.py) with a single `scope="class"`
autouse fixture, using class-level `django_db(transaction=True)` to persist seed
data across the 5 tests, with "TRUNCATE once at class teardown".

This mechanism is **incompatible with pytest-django's isolation model** and was
therefore not implemented.

## Root cause

In pytest-django, `django_db(transaction=True)` marks a test as a Django
`TransactionTestCase`. Django's `TransactionTestCase` **flushes (truncates) all
tables after every test** (`_fixture_teardown`). Consequently a class-scoped
fixture that seeds once is not robust: its data is wiped after test 1, so tests
2–5 would observe an empty DB (or force a re-seed / cross-test pollution).
pytest-django does not offer a per-class "flush once at teardown" option.

## Affected modules

- `src/backend/apps/seed/tests/test_seed.py::TestSeedFilterCoverage`

## Risk / impact

Attempting the approach as-specified would break test isolation and/or silently
fail tests 2–5 in the nightly seed suite. Deferred; D-01 (image mock) already
delivers the dominant per-seed-run speedup.

## Suggested direction

If class/session-level seed reuse is ever wanted, options to evaluate:
1. Seed into a true session-scoped fixture + `django_db(transaction=True)` and
   make every consuming test a `TransactionTestCase` WITHOUT relying on
   cross-test persistence — not compatible with pytest-django as-is.
2. Seed once in a separate persisted dataset and have each test read-only —
   requires disabling the per-test flush, which pytest-django does not expose.
3. Accept per-test seeding (current state) now that the image pipeline is mocked.
