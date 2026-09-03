"""
Core models for Mko Bazuna.

Provides shared singleton models used across apps.
"""

from django.db import models


class SiteConfig(models.Model):
    """
    Site name singleton for centralized branding (Problem 03).

    Exactly one row exists (pk=1). Edited by admin at runtime via Django
    admin. The site name is read through a cache layer on every request
    that renders a page title or `<title>` tag.
    """

    name = models.CharField(
        max_length=255,
        default="Bazuna",
        help_text="Site name displayed in page titles and headers",
    )

    class Meta:
        db_table = "site_config"
        verbose_name = "Site Config"
        verbose_name_plural = "Site Config"

    def __str__(self) -> str:
        return str(self.name)

    @classmethod
    def get_singleton(cls) -> SiteConfig:
        """Get the singleton instance, creating it if necessary."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
