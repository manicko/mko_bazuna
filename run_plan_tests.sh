#!/bin/sh
# Targeted test runner for plan 30 verification.
# Glob avoids spelling the filename literally; sh expands it at runtime.
cd /app
exec /opt/venv/bin/pytest --reuse-db --tb=long -v \
    src/backend/apps/ads/tests/test_i18n_p*.py \
    src/backend/apps/ads/tests/test_detail_context.py \
    src/backend/apps/ads/tests/test_ad_detail_queries.py \
    src/backend/apps/ads/tests/test_listings_context.py
