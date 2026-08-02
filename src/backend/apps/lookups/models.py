"""
LookupGroup and LookupItem models for the universal reference data system.

LookupGroup defines a named group of reference data (e.g. "listing_purpose").
LookupItem defines individual values within a group (e.g. "sell", "rent").
"""

from django.db import models


class LookupGroup(models.Model):
    """A named group of reference data values.

    Examples: listing_purpose, listing_feature.
    System groups (is_system=True) are protected from admin deletion.
    """

    code = models.CharField(
        max_length=100,
        unique=True,
        help_text="Machine-readable, immutable group code",
    )
    name_i18n = models.JSONField(
        null=True,
        blank=True,
        help_text="Localized names: {'ru': str, 'bs': str, 'en': str}",
    )
    is_system = models.BooleanField(
        default=False,
        help_text="Protected from admin deletion",
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "lookup_groups"
        ordering = ["sort_order"]
        verbose_name = "lookup group"

    def __str__(self) -> str:
        return self.code


class LookupItem(models.Model):
    """An individual value within a LookupGroup.

    Slug is globally unique across all groups.
    """

    group = models.ForeignKey(
        LookupGroup,
        on_delete=models.CASCADE,
        related_name="items",
        help_text="Parent lookup group",
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="Globally unique identifier",
    )
    name_i18n = models.JSONField(
        null=True,
        blank=True,
        help_text="Localized names: {'ru': str, 'bs': str, 'en': str}",
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive items are hidden from UI and filter options",
    )
    icon = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Emoji or SVG icon name",
    )
    color = models.CharField(
        max_length=7,
        blank=True,
        default="",
        help_text="Hex color code, e.g. #RRGGBB",
    )

    class Meta:
        db_table = "lookup_items"
        ordering = ["group", "sort_order"]
        verbose_name = "lookup item"

    def __str__(self) -> str:
        return self.slug