#!/bin/sh
# Verify filter/sort-related tests pass alongside the plan changes.
cd /app
echo "=== uv sync ==="
uv sync --frozen --no-install-project --group dev 2>&1 | tail -2
echo "=== pytest ==="
/opt/venv/bin/pytest --reuse-db --tb=short -v \
    src/backend/apps/ads/tests/test_catalog_filters.py \
    src/backend/apps/ads/tests/test_listings_sort.py \
    src/backend/apps/ads/tests/test_ad_localization.py
