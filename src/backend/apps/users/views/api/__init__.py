"""JSON API views for the ``users`` app.

``POST /api/v1/consent/{accept,decline,withdraw}/`` and
``POST /api/v1/auth/logout/`` (S3.3), mounted by ``apps/api/urls.py`` at the
``/api/v1/`` root via ``apps/users/api_urls.py``.
"""
