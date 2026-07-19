# Core app for shared utilities, abstract models, managers, signals, and enums.
from apps.core.enums import (  # noqa: F401
    AdSource,
    AdStatus,
    AnalyticsEventType,
    CategoryRejectReason,
    ModeratorActionType,
)

default_app_config = "apps.core.apps.CoreConfig"
