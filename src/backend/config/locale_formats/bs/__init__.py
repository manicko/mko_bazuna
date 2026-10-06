"""Bosnian (``bs``) project-level format overrides.

This package exists solely to supply ``NUMBER_GROUPING``, which Django's
bundled ``django.conf.locale.bs.formats`` leaves commented out. Every other
format attribute (``DECIMAL_SEPARATOR``, ``THOUSAND_SEPARATOR``, date and time
patterns, …) is still read from the bundled module because
``get_format`` resolves per-attribute against the first module that defines it.
"""
