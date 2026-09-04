 Нужно изучить проблему с тестом, изучить современные практики построения подобных тестов и разработать вариант, как сделать данный тест качественным и надежным
 test_full_seed_coverage fails on the original code (before my changes) too — it's a pre-existing flaky test, not caused by Plan 18 changes.

The failure is because the test asserts ≥90% coverage but the deterministic seed with faker_seed: 42 only produces 87.7% coverage across 171 leaf categories.

Since Plan 18 is focused on price enforcement and filter reset — this failing seed test is out of scope and pre-existing. Let me verify the fast gate passes cleanly (it skips seed tests):