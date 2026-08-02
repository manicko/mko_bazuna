"""
Category model for Mko Bazuna.

Hierarchical category tree using django-mptt (single source of truth).
"""


from apps.lookups.enums import LookupGroupCode
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


class CategoryPath(models.Model):
    """Alternative parent route for multi-parent navigation.

    Each category can have zero or more alternative parent routes
    while maintaining a single canonical MPTT parent.
    CategoryPath entries are NOT MPTT-managed — they are simple
    navigation shortcuts.
    """

    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="alternative_parents",
        help_text="The leaf/child being navigated to",
    )
    parent = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="alternative_children",
        help_text="The alternative parent in the navigation path",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Ordering within alternative parent's children",
    )
    is_automatic = models.BooleanField(
        default=False,
        help_text="True if created by system rule (e.g. price=0 -> Благотворительность)",
    )

    class Meta:
        db_table = "category_paths"
        unique_together = [("category", "parent")]
        ordering = ["sort_order"]
        verbose_name_plural = "category paths"

    def __str__(self) -> str:
        return f"{self.category.slug} -> {self.parent.slug}"

    def clean(self) -> None:
        """Validate: category != parent and no self-reference."""
        from django.core.exceptions import ValidationError

        if self.category_id == self.parent_id:
            raise ValidationError("A category cannot be an alternative parent of itself")


class CategoryListingPurpose(models.Model):
    """M:N through table binding a Category to a listing purpose LookupItem.

    Defines which listing purposes are available for this category.
    One purpose per category can be marked as default.
    """

    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="listing_purposes",
    )
    listing_purpose = models.ForeignKey(
        "lookups.LookupItem",
        on_delete=models.CASCADE,
        limit_choices_to={"group__code": LookupGroupCode.LISTING_PURPOSE},
        related_name="category_purposes",
    )
    is_default = models.BooleanField(
        default=False,
        help_text=(
            "Default purpose for this category; "
            "auto-selected when seller doesn't choose explicitly"
        ),
    )

    class Meta:
        db_table = "category_listing_purposes"
        unique_together = [("category", "listing_purpose")]
        indexes = [
            models.Index(fields=["category", "listing_purpose"]),
            models.Index(fields=["listing_purpose"]),
        ]
        verbose_name_plural = "category listing purposes"

    def __str__(self) -> str:
        return f"{self.category.slug} -> {self.listing_purpose.slug}"


class CategoryListingFeature(models.Model):
    """M:N through table binding a Category to a listing feature LookupItem.

    Defines which listing features are available for this category.
    """

    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="listing_features",
    )
    feature = models.ForeignKey(
        "lookups.LookupItem",
        on_delete=models.CASCADE,
        limit_choices_to={"group__code": LookupGroupCode.LISTING_FEATURE},
        related_name="category_features",
    )

    class Meta:
        db_table = "category_listing_features"
        unique_together = [("category", "feature")]
        indexes = [
            models.Index(fields=["category", "feature"]),
            models.Index(fields=["feature"]),
        ]
        verbose_name_plural = "category listing features"

    def __str__(self) -> str:
        return f"{self.category.slug} -> {self.feature.slug}"
