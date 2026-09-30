"""
Ad-creation data service for the Telegram bot.

A façade package that re-exports the concern-focused submodules:

* ``orm`` — DB helpers (``sync_to_async``): ``create_draft_ad``, ``delete_draft``,
  lookups, etc.
* ``media`` — bounded photo download + atomic staging writes.
* ``translation`` — parallel multi-language translation orchestration.
* ``feature_helpers`` — purpose / feature / condition resolution + lookups.
* ``keyboards`` — inline-keyboard builders.

Import direction: bot -> backend. Submodules import from ``apps.*`` or
``telegram_bot.schemas.*`` only — never from a sibling ``ad_data.*`` submodule.

All fixed values are constants — callback tokens via ``BotCallbackPrefix`` and
locale codes via ``LanguageLocale`` — per project rule 10. Keyboard button
labels that are user-facing literals are wrapped in ``gettext`` per rule 16.
"""

from telegram_bot.services.ad_data.feature_helpers import (
    get_default_purpose,
    get_feature_names,
    get_lookup_item,
    get_lookup_item_by_slug,
    get_resolved_conditions,
    get_resolved_features,
    get_resolved_purposes,
)
from telegram_bot.services.ad_data.keyboards import (
    build_condition_keyboard,
    build_currency_keyboard,
    build_feature_keyboard,
    build_purpose_keyboard,
)
from telegram_bot.services.ad_data.media import (
    download_photo,
    save_photo,
    touch_staging_photos,
)
from telegram_bot.services.ad_data.orm import (
    _get_ad_status,
    create_draft_ad,
    delete_draft,
    get_all_cities,
    get_category,
    get_city,
    get_city_by_name,
    search_categories,
    touch_draft,
)
from telegram_bot.services.ad_data.translation import translate_all_languages

# Re-export surface preserved verbatim from the original ad_data.py module so
# that all 32 importers across the codebase keep resolving names from
# ``telegram_bot.services.ad_data`` unchanged. ``delete_photo`` is deliberately
# absent: it is an imported name used internally by ``orm.delete_draft`` and is
# resolved through ``orm``'s module globals (patch targets must use
# ``telegram_bot.services.ad_data.orm.delete_photo``).
__all__ = [
    "create_draft_ad",
    "_get_ad_status",
    "delete_draft",
    "touch_draft",
    "search_categories",
    "get_city_by_name",
    "get_all_cities",
    "download_photo",
    "save_photo",
    "touch_staging_photos",
    "get_category",
    "get_city",
    "translate_all_languages",
    "get_resolved_purposes",
    "get_resolved_features",
    "get_resolved_conditions",
    "get_default_purpose",
    "get_lookup_item_by_slug",
    "get_lookup_item",
    "get_feature_names",
    "build_currency_keyboard",
    "build_purpose_keyboard",
    "build_condition_keyboard",
    "build_feature_keyboard",
]
