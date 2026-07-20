"""
City model for Mko Bazuna.

Location reference data with i18n name support.
"""


from django.db import models


class City(models.Model):
    """
    City for ad location.

    Russian name is base storage language. i18n names via JSONB.
    Match is EXACT against closed list; unrecognized → "general / no city".
    """

    country_code = models.CharField(
        max_length=2,
        help_text="ISO country code (e.g., 'BA' for Bosnia)",
    )
    name = models.CharField(
        max_length=200,
        help_text="Russian city name (base storage language)",
    )
    name_i18n = models.JSONField(
        blank=True,
        null=True,
        help_text="i18n names: {'ru': <str>, 'bs': <str>}; NULL falls back to name",
    )
    region = models.CharField(
        max_length=100,
        help_text="Administrative region",
    )
    slug = models.SlugField(
        unique=True,
        help_text="URL-friendly city slug",
    )

    class Meta:
        db_table = "cities"
        verbose_name_plural = "cities"

    def get_name(self, locale: str = "ru") -> str:
        """Get localized name with Russian fallback."""
        # At runtime, name_i18n is a dict or None
        name_i18n = getattr(self, "name_i18n", None)
        if name_i18n and locale in name_i18n:
            return name_i18n[locale]
        return str(self.name)

    def __str__(self) -> str:
        return str(self.name)