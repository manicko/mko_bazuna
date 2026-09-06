---
name: audit-findings
description: Structured findings for Block 1 bot_username migration audit
agent: audit-executor
phase: 11-bot-username-migration
status: complete
validated: no
---

# Phase 11 Audit Findings — Block 1: Migrate `bot_username` to `SiteConfig` singleton

**Executor:** audit-executor
**Status:** complete
**Validated:** no

---

## 0. HEADLINE VERDICT — Data layer is DONE; consumer migration is INCOMPLETE

The `bot_username` migration is **already implemented end-to-end at the data layer**
and is *not* greenfield work. The following artifacts were created on **2026-09-06**
(the migration file mtime), meaning a prior step completed them:

- `apps/core/models.py` — `bot_username` field already present (L26-36)
- `apps/core/migrations/0003_add_bot_username.py` — already exists, adds field + seeds from `settings.BOT_USERNAME`
- `apps/core/services/site_config.py` — `get_bot_username()` / `get_bot_username_async()` already present (L42-75)
- `apps/core/utils/cache.py` — site-config cache utils already mention `bot_username`
- `apps/core/signals.py` — `post_save` invalidation already in place
- `apps/core/admin.py` — `list_display` already includes `bot_username`
- `apps/core/services/__init__.py` — both service functions already exported

**However, the migration is NOT wired into its consumers.** The implementor's actual
remaining work is the *consumer* migration, not the data-layer mirroring described in
the task brief. This discrepancy is the single most important finding (see
F-BU-001). The verbatim pattern the consumer calls must mirror is documented in
Section 1 below.

---

## 1. VERBATIM PATTERN REFERENCE (for mirroring `get_bot_username`)

### 1.1 `SiteConfig` model + `get_singleton()` — `apps/core/models.py`

```python
from django.core.validators import RegexValidator
from django.db import models

class SiteConfig(models.Model):
    """..."""

    name = models.CharField(
        max_length=255,
        default="Bazuna",
        help_text="Site name displayed in page titles and headers",
    )

    bot_username = models.CharField(
        max_length=255,
        default="bazuna_bot",
        help_text="Telegram bot username without @ prefix",
        validators=[
            RegexValidator(
                regex=r"^[A-Za-z0-9_]{3,32}$",
                message="Bot username must be 3-32 characters, alphanumeric and underscore only",
            ),
        ],
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
```

**`RegexValidator` import/style:** `from django.core.validators import RegexValidator`
(models.py:7; migrations:9). Pattern `^[A-Za-z0-9_]{3,32}$`, message ends with no
trailing period. Store *without* `@` prefix (help_text states this).

### 1.2 `get_site_name()` / `get_site_name_async()` — `apps/core/services/site_config.py`

```python
import logging
from typing import cast

from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

def get_site_name() -> str:
    """Return the admin-configured site name (cached, 1h TTL).

    Falls back to 'Bazuna' if the DB or cache is unavailable (R-SN-05).
    """
    from apps.core.utils.cache import (
        get_cached_site_config,
        set_cached_site_config,
    )
    from apps.core.models import SiteConfig

    cached = get_cached_site_config()
    if cached:
        name = cached.get("name")
        if name:
            return name
    try:
        obj = SiteConfig.get_singleton()
        name = cast(str, obj.name)
        set_cached_site_config({"name": name, "bot_username": obj.bot_username})
        return name
    except Exception:
        logger.warning("SiteConfig unavailable; falling back to 'Bazuna'")
        return "Bazuna"

async def get_site_name_async() -> str:
    """Async wrapper for bot handlers — runs get_site_name in a thread."""
    return await sync_to_async(get_site_name)()
```

> **Note:** `get_bot_username()` / `get_bot_username_async()` ALREADY mirror this
> exactly (site_config.py:42-75). The cache dict stored by `get_bot_username`
> is `{"name": obj.name, "bot_username": bot_username}` (L61). The implementor
> does **not** need to add these functions — they exist verbatim.

### 1.3 `get_bot_username()` / `get_bot_username_async()` — `apps/core/services/site_config.py` (EXISTS)

```python
def get_bot_username() -> str:
    """Return the admin-configured Telegram bot username (cached, 1h TTL).

    Falls back to 'bazuna_bot' if the DB or cache is unavailable (R-SN-05).
    """
    from apps.core.utils.cache import (
        get_cached_site_config,
        set_cached_site_config,
    )
    from apps.core.models import SiteConfig

    cached = get_cached_site_config()
    if cached:
        bot_username = cached.get("bot_username")
        if bot_username:
            return bot_username
    try:
        obj = SiteConfig.get_singleton()
        bot_username = cast(str, obj.bot_username)
        set_cached_site_config({"name": obj.name, "bot_username": bot_username})
        return bot_username
    except Exception:
        logger.warning("SiteConfig unavailable; falling back to 'bazuna_bot'")
        return "bazuna_bot"


async def get_bot_username_async() -> str:
    """Async wrapper for bot handlers — runs get_bot_username in a thread."""
    return await sync_to_async(get_bot_username)()
```

### 1.4 Cache utilities — `apps/core/utils/cache.py` (EXISTS, already mentions `bot_username`)

```python
from typing import Final
from django.core.cache import cache

SITE_CONFIG_CACHE_KEY: Final[str] = "site_config:v1"
SITE_CONFIG_CACHE_TTL: Final[int] = 3600  # 1 hour

def get_cached_site_config(key: str = SITE_CONFIG_CACHE_KEY) -> dict | None:
    return cache.get(key)

def set_cached_site_config(
    value: dict,
    key: str = SITE_CONFIG_CACHE_KEY,
    ttl: int = SITE_CONFIG_CACHE_TTL,
) -> None:
    cache.set(key, value, ttl)

def invalidate_site_config(key: str = SITE_CONFIG_CACHE_KEY) -> None:
    cache.delete(key)
```

### 1.5 Signal receiver — `apps/core/signals.py` (EXISTS)

```python
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.core.models import SiteConfig
from apps.core.utils.cache import invalidate_site_config

logger = logging.getLogger(__name__)

@receiver(post_save, sender=SiteConfig)
def invalidate_site_config_cache_on_save(sender, instance, **kwargs):
    """..."""
    logger.info("Invalidating site config cache after save")
    invalidate_site_config()
```

Registered via `CoreConfig.ready()` → `import apps.core.signals`
(`apps/core/apps.py:18-20`). Because the cached dict holds *both* `name` and
`bot_username`, this single invalidation covers the new field — **no new signal
is needed** (confirmed by research doc `.ai/research/04_telegram-contact-antispam-research.md:468`).

### 1.6 Admin — `apps/core/admin.py` (EXISTS, already lists `bot_username`)

```python
from apps.core.models import SiteConfig
from django.contrib import admin

@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    """..."""
    list_display = ["name", "bot_username"]
    readonly_fields = []

    def has_add_permission(self, request) -> bool:
        # Singleton - row created automatically if missing
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
```

> No `fieldsets` or `help_texts` are defined. `help_text` lives on the model
> field (L32: "Telegram bot username without @ prefix"). The implementor mirroring
> `name` adds nothing new here.

### 1.7 Seed migration pattern — `apps/core/migrations/0002_seed_default.py` (model seed) vs `0003_add_bot_username.py` (the new field)

`0002` established the singleton row:
```python
def seed_site_config(apps, schema_editor):
    SiteConfig = apps.get_model("core", "SiteConfig")
    SiteConfig.objects.get_or_create(pk=1, defaults={"name": "Bazuna"})

class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunPython(seed_site_config, reverse_code=migrations.RunPython.noop)]
```

`0003` (the field migration — **already committed today**) replicates exactly:
```python
def seed_bot_username(apps, schema_editor):
    SiteConfig = apps.get_model("core", "SiteConfig")
    # Read BOT_USERNAME from settings; fall back to "bazuna_bot" if empty.
    from django.conf import settings as dj_settings
    bot_username = getattr(dj_settings, "BOT_USERNAME", "") or "bazuna_bot"
    SiteConfig.objects.filter(pk=1).update(bot_username=bot_username)

class Migration(migrations.Migration):
    dependencies = [("core", "0002_seed_default")]
    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="bot_username",
            field=models.CharField(
                default="bazuna_bot",
                help_text="Telegram bot username without @ prefix",
                max_length=255,
                validators=[
                    RegexValidator(
                        message="Bot username must be 3-32 characters, alphanumeric and underscore only",
                        regex="^[A-Za-z0-9_]{3,32}$",
                    ),
                ],
            ),
        ),
        migrations.RunPython(seed_bot_username, reverse_code=migrations.RunPython.noop),
    ]
```

Pattern notes for an implementor: reads settings via
`getattr(dj_settings, "BOT_USERNAME", "") or "<default>"`; uses
`filter(pk=1).update(...)` (not `get_or_create`, since the row already exists);
`reverse_code=migrations.RunPython.noop`.

### 1.8 Consumer call sites that STILL use `settings.BOT_USERNAME` (the open work)

| File | Line | Verbatim |
|------|------|----------|
| `apps/core/views.py` | 31 | `{"bot_username": settings.BOT_USERNAME},` (inside `privacy_policy()` `render()`) |
| `apps/ads/views/listings.py` | 90 | `"bot_username": settings.BOT_USERNAME,` (inside `ad_detail()` `context` dict) |
| `apps/users/views/consent.py` | 306-307 | `bot_username = settings.BOT_USERNAME` / `deep_link = f"https://t.me/{bot_username}?start=login_{raw_token}"` (inside `login_issue()`) |

**Context processor `site_config()` (apps/core/context_processors.py:112-116) returns ONLY `{"site_name": get_site_name()}` — it does NOT inject `bot_username`.**

**`header_context()` docstring (apps/core/context_processors.py:45-48) is INACCURATE:**
> `- ``bot_username``: Telegram bot username for the place-an-ad deep-link. Resolved at render time via the ``telegram_deep_link`` template tag using the ``get_bot_username()`` service (cached, 1h TTL). Templates must never reference ``settings.BOT_USERNAME`` directly.`

But the actual `header_context()` return dict (L93-108) contains no `bot_username` key,
and **no `telegram_deep_link` template tag exists** (see F-BU-004). The docstring
describes a feature that is not implemented.

### 1.9 `BOT_USERNAME` settings definition — `src/backend/config/settings/base.py:234`

```python
# Telegram Bot username for contact deep-links
# Format: without @ prefix, e.g., "MyBot" not "@MyBot"
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
```

### 1.10 Bot-side async usage of `get_site_name_async` (mirror target for `get_bot_username_async`)

| File | Line | Verbatim |
|------|------|----------|
| `src/telegram_bot/handlers/ad_create.py` | 41 (import) | `from apps.core.services.site_config import get_site_name_async` |
| `src/telegram_bot/handlers/ad_create.py` | 124 | `f"Welcome to {await get_site_name_async()}! Creating new ad. Please select a category.\n"` |
| `src/telegram_bot/handlers/login.py` | 21 (import) | `from apps.core.services.site_config import get_site_name_async` |
| `src/telegram_bot/handlers/login.py` | 49 | `f"Welcome to {await get_site_name_async()}! To login, use a deep-link: /start login_<your_token>"` |

> **`get_bot_username_async` is NEVER called anywhere in the bot** (grep for
> `get_bot_username` returns matches only in `services/site_config.py`,
> `services/__init__.py` (export), and docs). It is defined-but-unconsumed.

### 1.11 Templatetags directory

`apps/core/templatetags/` EXISTS with: `__init__.py`, `contact_tags.py`,
`dict_tags.py`, `localized_content.py`. There is **NO `telegram_tags.py`** — the
`telegram_deep_link` tag referenced in the `header_context` docstring and in
`.ai/research/...research.md:478` / `.ai/problems/18_contact-us_spec.md:599` does
**not** exist.

### 1.12 Base template / footer structure (confirmed, shallow)

- No `base.html` exists under `src/backend/templates/` (greps for `*base*` found
  only `admin/base_site.html` in admin templates).
- Templates compose via `{% include "components/header.html" %}`,
  `{% include "components/header_catalog.html" %}`, `{% include "components/footer.html" %}`.
- `templates/components/footer.html` (11 lines) renders `&copy; 2026 {{ site_name }}`
  and links to `core:privacy` + cookie settings — does NOT reference `bot_username`.
- `templates/components/header.html` (28 lines) uses `{{ site_name }}` + `{% url %}`.
- `templates/components/header_catalog.html:33` uses `{{ bot_username }}` for the
  "Submit an ad" deep-link:
  `href="https://t.me/{{ bot_username }}?start=create_ad"`.
- `templates/ads/detail.html:167` uses `{{ bot_username }}` for the contact button:
  `href="https://t.me/{{ bot_username }}?start=contact_{{ ad.id }}"`.
- `templates/privacy.html:30,33,111,148,151` uses `{{ bot_username }}`.

**Critical implication:** `header_catalog.html` (rendered on catalog/search pages)
consumes `{{ bot_username }}`, but `listings()` view (ads/views/listings.py:435-456)
does **not** pass `bot_username` in its context. It only renders correctly today
because `header_context` historically injected it — and per F-BU-003 the consumer
contract is now inconsistent.

---

## 2. Findings

### F-BU-001: View consumers still read `settings.BOT_USERNAME` instead of `get_bot_username()`

| Field | Value |
|-------|-------|
| **ID** | F-BU-001 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/core/views.py`, `src/backend/apps/ads/views/listings.py`, `src/backend/apps/users/views/consent.py` |
| **Classification** | mandatory |

**Description:** The site-name migration pattern (cache → `get_site_name()` →
context processor) is the established convention, and `bot_username` now has an
identical `get_bot_username()` service. Yet three views bypass the service and read
the env-var-backed setting directly:

- `apps/core/views.py:31` — `privacy_policy()` → `{"bot_username": settings.BOT_USERNAME}`
- `apps/ads/views/listings.py:90` — `ad_detail()` → `"bot_username": settings.BOT_USERNAME`
- `apps/users/views/consent.py:306-307` — `login_issue()` → `bot_username = settings.BOT_USERNAME`; `deep_link = f"https://t.me/{bot_username}?start=login_{raw_token}"`

**Impact:** This defeats the entire migration's purpose. An admin who edits
`SiteConfig.bot_username` in Django admin invalidates the cache via the `post_save`
receiver (signals.py:18), but these three call sites never read the cache or
`SiteConfig` — they read the static env var. Result: admin edits to the bot username
silently fail to propagate to 3 of the 4 deep-link surfaces (privacy, ad-detail
contact, login deep-link). Buyer-stories.md AC5
("Bot username is resolved from SiteConfig (not settings.BOT_USERNAME) via
get_bot_username()") is violated.

**Evidence:**
- views.py:31 `{"bot_username": settings.BOT_USERNAME}`
- listings.py:90 `"bot_username": settings.BOT_USERNAME`
- consent.py:306 `bot_username = settings.BOT_USERNAME`
- Contrast: `get_site_name` is consumed via `site_config()` context processor
  (context_processors.py:114-116) for the site name — the symmetric consumer is
  missing for `get_bot_username`.

**Recommendation:** Replace `settings.BOT_USERNAME` in all three views with
`get_bot_username()` (sync) — imported from `apps.core.services.site_config`.
This mirrors exactly how `site_config()` context processor calls `get_site_name()`.
Effort: small. Priority: mandatory (correctness of the migration).

---

### F-BU-002: `site_config()` context processor returns `site_name` only — `bot_username` not injected

| Field | Value |
|-------|-------|
| **ID** | F-BU-002 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/core/context_processors.py`, `src/backend/templates/components/header_catalog.html` |
| **Classification** | mandatory |

**Description:** The `site_config()` context processor (the symmetric equivalent for
`get_site_name`) returns only `{"site_name": get_site_name()}` (L112-116). It does
NOT return `bot_username`. Yet `header_catalog.html:33` (rendered on every
catalog/search/detail page that includes the catalog header) references
`{{ bot_username }}`. The only views that currently satisfy this are
`ad_detail()` and `privacy_policy()` / `login_issue()` — the `listings()` view
(L435-456) does **not** pass `bot_username`, so the "Submit an ad" button's
`href="https://t.me/{{ bot_username }}?start=create_ad"` renders with an empty
username on listing pages.

This is a latent rendering defect masked today only because the migration has not
rewired the views. Once F-BU-001 is fixed to use `get_bot_username()`, this gap
becomes a hard dependency: either the context processor must inject `bot_username`
(or a template tag must resolve it), or listing pages break.

**Evidence:**
- context_processors.py:112-116 (`site_config` returns `{"site_name": ...}` only)
- context_processors.py:45-48 (docstring claims `bot_username` is resolved — false)
- listings.py:87-97 (`ad_detail` context has no `bot_username` issue; but
  `listings()` at L435-456 has NO `bot_username` key at all)
- header_catalog.html:6 (comment: "Context: bot_username + root_categories (context processor)") and :33 (`{{ bot_username }}`)

**Recommendation:** Either (a) extend `site_config()` context processor to also
return `{"bot_username": get_bot_username()}`, or (b) introduce the
`telegram_deep_link` template tag (referenced but absent — see F-BU-004) that
resolves `get_bot_username()` at render time. Option (a) mirrors the existing
`site_name` convention and is the lower-effort, lower-coupling choice for the MVP.
Effort: small. Priority: recommended before F-BU-001 so listing pages remain intact.

---

### F-BU-003: `header_context()` docstring contradicts its return dict (aspirational `bot_username` injection)

| Field | Value |
|-------|-------|
| **ID** | F-BU-003 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION / DOC-UPDATE |
| **Affected Modules** | `src/backend/apps/core/context_processors.py` |
| **Classification** | advisory |

**Description:** `header_context()` docstring (L45-48) advertises `bot_username`
as a context variable "resolved at render time via the `telegram_deep_link` template
tag using the `get_bot_username()` service", and instructs "Templates must never
reference `settings.BOT_USERNAME` directly." The actual return dict (L93-108)
contains only: `root_categories`, `preferred_city_display`, `cities`,
`favorites_count`, `catalog_js_labels` — no `bot_username`. The docstring
documents behavior that is not implemented, which misleads any reader into
believing templates receive `bot_username` from the context processor.

**Evidence:**
- context_processors.py:45-48 (docstring bullet for `bot_username`)
- context_processors.py:93-108 (actual `return {...}` — no `bot_username` key)

**Recommendation:** Either implement what the docstring promises (inject
`bot_username` or document the tag) or correct the docstring to state that
`bot_username` is supplied per-view (and list the views). Doc drift is medium
risk because template authors rely on this contract. Per the dead-code/dead-doc
policy, an inaccurate contract doc should be fixed. Effort: trivial. Priority:
advisory.

---

### F-BU-004: `telegram_deep_link` template tag referenced but not implemented

| Field | Value |
|-------|-------|
| **ID** | F-BU-004 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/core/templatetags/`, `src/backend/apps/core/context_processors.py` |
| **Classification** | advisory |

**Description:** The `header_context` docstring (L46-47) and research doc
(04_telegram-contact-antispam-research.md:478) reference a `telegram_deep_link`
template tag in `apps/core/templatetags/telegram_tags.py`. That file does **not**
exist: the templatetags package contains only `__init__.py`, `contact_tags.py`,
`dict_tags.py`, `localized_content.py`. No `telegram_deep_link`, `telegram_tags`,
or `register.simple_tag`/inclusion tag for deep-links exists anywhere in the tree
(`grep` for `telegram_deep_link` returns matches only in docs and the docstring).

**Implication:** If F-BU-002 is resolved by route (a) (context processor inject),
this is a non-issue. If the intended design is route (b) (tag), the tag must be
created. The existing tag style to mirror: `dict_tags.py` uses
`register = template.Library()` + `@register.simple_tag` / `@register.filter`
(L20-46). An implementor creating `telegram_tags.py` should follow that style.

**Evidence:**
- `apps/core/templatetags/` listing: `__init__.py`, `contact_tags.py`, `dict_tags.py`, `localized_content.py` (no `telegram_tags.py`)
- contact_processors.py:46-47 docstring references `telegram_deep_link` tag
- research md:478 "Create `apps/core/templatetags/telegram_tags.py`"

**Recommendation:** Decide the resolution strategy (context var vs. tag) and
either implement the tag (mirroring `dict_tags.py` registration style) or remove
the stale docstring reference. Effort: medium if tag created; trivial if doc-only
correction. Priority: recommended.

---

### F-BU-005: `get_bot_username` / `get_bot_username_async` defined but never consumed

| Field | Value |
|-------|-------|
| **ID** | F-BU-005 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/core/services/site_config.py`, `src/backend/apps/core/services/__init__.py`, `src/telegram_bot/` |
| **Classification** | advisory |

**Description:** `get_bot_username` (site_config.py:42-65) and
`get_bot_username_async` (site_config.py:73-75) are implemented, exported in
`services/__init__.py:11-12,25-26`, and documented as the intended service in
buyer-stories.md AC5 and the research doc — but a repo-wide grep shows they are
**never imported or called in any production code path**. `get_site_name_async`
has two bot call sites (ad_create.py:124, login.py:49); the bot username
equivalent has zero. This is "documented future-proofing" (not dead code per the
dead-code policy) but it means the service exists with no coverage.

**Evidence:** `grep -rn "get_bot_username"` → only
`services/site_config.py` (def), `services/__init__.py` (export), and
`.ai/*` docs. No `telegram_bot/handlers/**` import.

**Recommendation:** Wire `get_bot_username_async` into the bot handlers that build
deep-links (login.py, ad_create.py), or at minimum add a unit test mirroring
`test_site_config.py`'s `get_site_name` tests for the bot_username variant.
Effort: small for tests; medium for bot wiring. Priority: recommended.

---

### F-BU-006: Tests pin the old `settings.BOT_USERNAME` consumer behavior — no coverage for `get_bot_username`

| Field | Value |
|-------|-------|
| **ID** | F-BU-006 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/ads/tests/test_detail_context.py`, `src/backend/apps/ads/tests/test_detail_render.py`, `src/backend/apps/core/tests/test_site_config.py` |
| **Classification** | mandatory |

**Description:** Existing tests assert against the *old* `settings.BOT_USERNAME`
contract, so migrating consumers (F-BU-001) will flip them:

- `test_detail_context.py:107-111` — `test_detail_context_contains_bot_username`:
  `assert context["bot_username"] == settings.BOT_USERNAME`
- `test_detail_context.py:133-140` — `test_detail_template_uses_bot_username_not_settings`:
  asserts `"{{ bot_username }}" in content` and `"settings.BOT_USERNAME" not in content`
  (template-level check only; the function `def test_detail_template_uses_bot_username_not_settings():`
  takes no parameters).
- `test_detail_render.py:67` — `expected_href = f"https://t.me/{settings.BOT_USERNAME}?start=contact_{ad.id}"`
- `test_site_config.py` — covers `get_site_name` (singleton, cache, fallback,
  signal invalidation, privacy render) but has **no equivalent for
  `get_bot_username`** despite the service existing.

Per project rule #2 ("Production code is king") and the research doc
(04_telegram-contact-antispam-research.md:474, 620), these tests must be updated to
use `get_bot_username()` / `SiteConfig.get_singleton().bot_username` rather than
`settings.BOT_USERNAME`. Test env has `BOT_USERNAME=""` (base.py:234 default),
so `test_detail_render.py:67` currently asserts a malformed
`https://t.me/?start=contact_1` href — a meaningless passing test.

**Evidence:** `test_detail_render.py:13` docstring "G4: ... `https://t.me/{bot_username}?start=...`",
`:67` assertion against `settings.BOT_USERNAME`.

**Recommendation:** Update the three assertions to resolve `bot_username` via the
service (with a `SiteConfig` fixture). Add `get_bot_username` tests mirroring
`test_site_config.py`'s `name` tests. Effort: small. Priority: mandatory (tests
otherwise regress / pin the wrong contract).

---

### F-BU-007: Env var retention — `BOT_USERNAME` is now a seed-only value

| Field | Value |
|-------|-------|
| **ID** | F-BU-007 |
| **Severity** | LOW |
| **Type** | DOC-UPDATE |
| **Affected Modules** | `config/settings/base.py:234`, `.env.example`, `.env.dev.example`, `.env.docker.example` |
| **Classification** | advisory |

**Description:** Per docs/01-spec and the research doc (18_contact-us_spec.md:233),
`BOT_USERNAME` env var is retained **as seed value only** for migration 0003
(`getattr(dj_settings, "BOT_USERNAME", "") or "bazuna_bot"`). The setting itself
remains at `config/settings/base.py:234`:
`BOT_USERNAME = os.getenv("BOT_USERNAME", "")`. After migration, runtime reads
should go through `get_bot_username()` (SiteConfig), not the env var.

**Risk:** If F-BU-001 is not completed, the env var remains a *live* runtime
source (not seed-only), undermining the migration. The env files
(`.env.example:36`, `.env.dev.example:32`, `.env.docker.example:25`) still list
`BOT_USERNAME` with no "seed-only" annotation, so deployers may believe editing
the env var at runtime is the supported path.

**Recommendation:** (a) Complete F-BU-001 so no runtime path reads the env var
directly; (b) annotate `BOT_USERNAME` in settings + env examples as
"seed value for the initial SiteConfig, editable in Django admin thereafter"
once consumers are migrated. Effort: trivial. Priority: recommended.

---

## 3. Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 1 (F-BU-001) |
| MEDIUM | 4 (F-BU-002, F-BU-003, F-BU-004, F-BU-006) |
| LOW | 2 (F-BU-005, F-BU-007) |

## Mandatory Fixes

- **F-BU-001** — Migrate the 3 view consumers (`views.py:31`, `listings.py:90`,
  `consent.py:306-307`) from `settings.BOT_USERNAME` to `get_bot_username()`.
- **F-BU-002** — Ensure `header_catalog.html`'s `{{ bot_username }}` resolves on
  listing pages (context processor or tag) — required for F-BU-001 completeness.
- **F-BU-006** — Update `test_detail_context.py`, `test_detail_render.py` to assert
  against the service/site-config, and add `get_bot_username` coverage in
  `test_site_config.py`.

## Advisory Recommendations

- F-BU-003 (docstring/return mismatch), F-BU-004 (missing `telegram_deep_link`
  tag — decide tag-vs-context-var strategy), F-BU-005 (consumed bot-side calls /
  tests), F-BU-007 (env-var-as-seed annotation).

## Doc Updates Needed

- F-BU-003 — reconcile `header_context` docstring with implementation.
- F-BU-004 — if tag route is rejected, remove `telegram_deep_link` docstring
  references; if adopted, document the tag's contract.
- F-BU-007 — mark `BOT_USERNAME` as seed-only in settings + `.env*` examples.

---

## 4. Reproduction / Verification Notes

- Run `make test-recreate` (fresh schema) — migration 0003 must apply cleanly
  and seed `bot_username` from `settings.BOT_USERNAME` (or `bazuna_bot`
  fallback). `test_migrations.py` (`test_makemigrations_check`) guards against
  schema drift, so any future field addition must include a new migration.
- `test_site_config.py` (unit/integration, `pytest.mark.django_db`) clears
  LocMemCache in an `autouse` fixture (L28-33) — new bot_username cache tests
  must use the same cache-clear discipline.
- Cache backend in prod is Redis (shared web+bot), LocMem in dev/test
  (base.py:257-265). `get_bot_username_async` thus reads the same shared cache
  as the web process — no separate cache key needed (single `site_config:v1`).
