"""Project-level locale format overrides.

Wired through Django's ``FORMAT_MODULE_PATH`` setting (see
``config/settings/base.py``). Django's format machinery resolves each format
attribute per-attribute: ``django.utils.formats.get_format`` iterates
``iter_format_modules()`` and returns the first module that defines the
requested attribute, so a module here overrides only the attributes it
declares while every other attribute still falls through to Django's bundled
locale data (``django.conf.locale.<lang>.formats``).

Only the ``bs`` subpackage is present. It supplies the one attribute that
Django's bundled Bosnian locale leaves undefined (``NUMBER_GROUPING``); all
other locales keep their bundled definitions untouched.
"""
