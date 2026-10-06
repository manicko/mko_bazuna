"""Bosnian number-format override.

Django's bundled ``django.conf.locale.bs.formats`` defines
``DECIMAL_SEPARATOR`` and ``THOUSAND_SEPARATOR`` but leaves
``NUMBER_GROUPING`` commented out. ``django.utils.numberformat`` gates
thousands grouping on ``use_grouping and grouping != 0``, so the absent
grouping value (which ``get_format`` defaults to ``0``) makes grouping
unreachable for ``bs`` even under ``force_grouping=True`` — round and
seven-digit amounts render ungrouped.

Only ``NUMBER_GROUPING = 3`` is declared here. The separators and every other
attribute continue to come from Django's bundled ``bs`` locale data, which is
never edited.
"""

NUMBER_GROUPING = 3
