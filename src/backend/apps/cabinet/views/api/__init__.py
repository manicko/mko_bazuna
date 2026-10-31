"""JSON API views for the ``cabinet`` app.

``GET /api/v1/favorites/`` (S2.4), ``GET /api/v1/saved-searches/`` and
``GET /api/v1/search-history/`` (S2.7), the saved-search write halves
``POST /api/v1/saved-searches/`` + ``POST /api/v1/saved-searches/{pk}/{toggle,
edit,delete}/`` (S3.4) and the search-history clear half
``POST /api/v1/search-history/clear/`` (S3.5).
"""
