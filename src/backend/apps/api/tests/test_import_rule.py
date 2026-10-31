"""R-F2 mechanical import-subset harness for the ``/api/v1/`` surface.

The ratified import rule (plan §2.3) is:

    An API view module's imports must be a **subset** of its mirrored HTML view
    module's imports, plus an explicit allowlist (``apps.core.utils.problem``,
    ``apps.core.utils.api_auth``) and all stdlib / ``django.*`` modules.

Rationale: the API view must reuse exactly the dependency edges its HTML mirror
already needs, so mounting ``/api/v1/`` can never introduce a new import cycle
(audit risk 6) and can never reach a service the HTML consumer does not use.

**Pairing table.** ``PAIRING_TABLE`` is the declared, explicit registry of
``(api_module_path, mirror_module_path)`` rows. It ships **empty** at S0.2;
every later endpoint task registers its row here in the same task that ships the
endpoint. With zero rows the harness passes trivially, which is the S0.2
acceptance criterion — but it is a live guard from day one.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Declared pairing table: (API view module, mirrored HTML view module).
# Rows are added by the endpoint tasks (S1.3+). Empty at S0.2.
PAIRING_TABLE: list[tuple[str, str]] = [
    # S1.3 — listings read. The API adapter mirrors the HTML listings view and
    # calls the exact same `ListingsQuery`/`build_listings_context` service tier.
    ("apps.ads.views.api.listings", "apps.ads.views.listings"),
    # S1.4 — FTS search read. The API adapter mirrors the HTML search view and
    # calls the exact same `apps.search.services.fts` pipeline + shared cache.
    ("apps.search.views.api.search", "apps.search.views.search"),
    # S1.5 — ad detail read. The API adapter mirrors the HTML `ad_detail` view
    # (which lives in `apps.ads.views.listings`) and applies the exact same
    # `account_state_q` audience predicate + `AD_VIEWED` side effect.
    ("apps.ads.views.api.detail", "apps.ads.views.listings"),
    # S1.6 — category tree read. The API adapter mirrors the HTML submenu view
    # (`apps.categories.views`) and reads the `Category` models directly (it
    # deliberately does NOT route through that view's rendered-fragment cache).
    ("apps.categories.api_tree", "apps.categories.views"),
    # S1.6 — cities read. The HTML consumer of the `locations` models is the
    # header context processor (a single module, not an app views module), so the
    # mirror is declared as `apps.core.context_processors`; the API module imports
    # the `locations` models only, exactly the import surface the mirror needs.
    ("apps.locations.api_cities", "apps.core.context_processors"),
    # S2.3 — dashboard read. The API adapter mirrors the HTML dashboard view and
    # consumes the exact same `ads_by_status` grouping service (S2.2) +
    # `SellerStats` aggregation. The consent gate is re-asserted through the
    # shared `can_create_ad` seam (A14), which is allowlisted below.
    ("apps.ads.views.api.dashboard", "apps.ads.views.dashboard"),
    # S2.4 — favorites list read. The API adapter mirrors the HTML cabinet
    # favorites list and consumes the exact same `favorites_queryset` shared
    # service (S2.1) with the same `PER_PAGE` page size.
    ("apps.cabinet.views.api.favorites", "apps.cabinet.views.favorites"),
]

# Modules an API view may import even though its HTML mirror does not.
#
# - `apps.core.utils.problem` / `apps.core.utils.api_auth`: the two shared
#   RFC 9457 / session-auth helpers the plan allows every `/api/v1/` view to use
#   (§2.3 import rule).
# - `apps.search.services.rate_limit`: the shared `rate_limit_check` +
#   `RateLimitBudget` single enforcement point (R1/Q4). The HTML listings view
#   happens to use the deep-link-render limiter instead, but the plan mandates
#   `rate_limit_check` with the dedicated `api_*` budgets for every `/api/v1/`
#   read route, so the API adapter must import it though its mirror does not.
# - `apps.core.schemas`: the mandated `BaseInputModel` base for every
#   client-input DTO. Both API adapters build their GET-dimension DTO on it
#   (the HTML views parse `request.GET` inline and never need the base), so it
#   is a shared `/api/v1/` helper, not a mirror-specific edge.
# - `apps.users.services.account_state`: the A14-mandated **shared consent
#   seam** (`can_create_ad`). The dashboard HTML mirror gates through its
#   view-local `_seller_may_create_ad` wrapper (which itself reaches
#   `can_create_ad` transitively via `apps.ads.views.edit`), but the API view is
#   forbidden by A14 from importing view privates: it must re-assert consent
#   through the shared predicate directly. That makes this a sanctioned shared
#   edge — the allowlist's exact purpose — not a mirror-specific import.
ALLOWLIST: frozenset[str] = frozenset(
    {
        "apps.core.utils.problem",
        "apps.core.utils.api_auth",
        "apps.search.services.rate_limit",
        "apps.core.schemas",
        "apps.users.services.account_state",
    }
)


def test_pairing_table_rows_satisfy_import_rule() -> None:
    """Every registered API module's imports are a subset of its mirror's."""
    for api_module_path, mirror_module_path in PAIRING_TABLE:
        api_imports = _imports_of(api_module_path)
        mirror_imports = _imports_of(mirror_module_path)
        allowed = mirror_imports | ALLOWLIST | _stdlib_and_django(api_imports)

        offending = sorted(api_imports - allowed)
        assert not offending, _violation_message(
            api_module_path, mirror_module_path, offending
        )


def test_pairing_table_has_no_duplicate_rows() -> None:
    """The pairing table must not register the same API module twice."""
    api_modules = [api_module for api_module, _ in PAIRING_TABLE]
    duplicates = sorted({m for m in api_modules if api_modules.count(m) > 1})
    assert not duplicates, f"Duplicate API modules in PAIRING_TABLE: {duplicates}"


def _imports_of(dotted_module_path: str) -> set[str]:
    """Return the absolute imported module names of a source module.

    ``dotted_module_path`` is a module such as ``apps.ads.views.api.listings``;
    it is resolved to a source file via ``src/backend`` on the file system.
    """
    source_path = _source_path_for(dotted_module_path)
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

    package_parts = dotted_module_path.split(".")
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                modules.add(_resolve_relative(node, package_parts))
            elif node.module:
                modules.add(node.module)
    return modules


def _source_path_for(dotted_module_path: str) -> Path:
    """Map a dotted module path to its ``.py`` file under ``src/backend``."""
    # ``test_import_rule.py`` lives at ``src/backend/apps/api/tests/``; walking
    # three parents up from the file's directory reaches ``src/backend``.
    backend_root = Path(__file__).resolve().parents[3]
    return backend_root.joinpath(*dotted_module_path.split(".")).with_suffix(".py")


def _resolve_relative(node: ast.ImportFrom, package_parts: list[str]) -> str:
    """Resolve a relative ``ImportFrom`` node to its absolute dotted name."""
    base = package_parts[: len(package_parts) - node.level]
    prefix = ".".join(base)
    if node.module:
        return f"{prefix}.{node.module}" if prefix else node.module
    return prefix


def _stdlib_and_django(imported: set[str]) -> set[str]:
    """Filter ``imported`` down to stdlib and ``django.*`` modules."""
    return {
        module
        for module in imported
        if module.split(".", 1)[0] == "django"
        or module.split(".", 1)[0] in sys.stdlib_module_names
    }


def _violation_message(
    api_module_path: str, mirror_module_path: str, offending: list[str]
) -> str:
    """Build a clear failure message listing the offending imports."""
    lines = [
        f"Import-rule violation for '{api_module_path}':",
        f"  its mirror is '{mirror_module_path}'.",
        "  The following imports are not in the mirror's imports and are not "
        "allowlisted:",
    ]
    lines.extend(f"    - {module}" for module in offending)
    lines.append(
        "  Fix: either reuse only the mirror's imports, or add the module to "
        "ALLOWLIST if it is a shared API helper."
    )
    return "\n".join(lines)
