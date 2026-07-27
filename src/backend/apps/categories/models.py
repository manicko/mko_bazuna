"""
Category model for Mko Bazuna.

Hierarchical category tree using django-mptt (single source of truth).
"""


from django.db import models
from mptt.models import MPTTModel, TreeForeignKey


class Category(MPTTModel):
    """
    Category tree for ads using django-mptt.

    Russian name is base storage language. i18n names via JSONB.
    """

    name = models.CharField(
        max_length=200,
        help_text="Russian category name (base storage language)",
    )
    name_i18n = models.JSONField(
        blank=True,
        null=True,
        help_text="i18n names: {'ru': <str>, 'bs': <str>, 'en': <str>}; NULL falls back to name",
    )
    slug = models.SlugField(
        unique=True,
        help_text="URL-friendly category slug",
    )
    is_active = models.BooleanField(
        default=True,  # pyright: ignore[reportArgumentType]
        help_text="Inactive categories hide their ads",
    )
    parent = TreeForeignKey(
        "self",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="children",
        help_text="Parent category for tree structure",
    )

    class MPTTMeta:
        order_insertion_by = ["name"]

    class Meta:
        db_table = "categories"
        verbose_name_plural = "categories"

    def get_name(self, locale: str = "ru") -> str:
        """Get localized name with fallback chain: locale → ru → name."""
        # At runtime, name_i18n is a dict or None
        name_i18n = getattr(self, "name_i18n", None)
        if name_i18n:
            if locale in name_i18n:
                return name_i18n[locale]
            if "ru" in name_i18n:
                return name_i18n["ru"]
        return str(self.name)

    def __str__(self) -> str:
        return str(self.name)
