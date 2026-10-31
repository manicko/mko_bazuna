"""URL-aggregator-only namespace for the ``/api/v1/`` JSON surface.

This package is **not** an installed Django app: it is absent from
``INSTALLED_APPS`` and holds no models, apps.py, services or views. It exists
solely to host ``apps/api/urls.py``, the URL-only aggregator that
``config/urls.py`` mounts under ``/api/v1/``. Per-app routes live in each app's
``<app>/api_urls.py`` module and are pulled in there via ``include()``.
"""
