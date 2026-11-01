"""Read-only rule-18 (agent-first) parity audit for the ``/api/v1/`` surface.

``verify_parity`` is the **poll-safe** tier of the API-parity verification
strategy (plan §5, layer 5): it replays the declared parity claims without
touching the database, writing files or recording analytics, so an agent (or
CI) can re-run it as often as it likes. It **never scheduled** — see
``HOURLY_COMMANDS`` / ``DAILY_COMMANDS`` in ``apps.core.utils.scheduler``, which
deliberately do not name this command.

What it checks (one ``OK``/``FAIL`` line per check, deterministic order):

``route_reversible``
    Every route under ``/api/v1/`` reverses back to itself (its namespace and
    name are declared, and ``path == reverse(name, args)``).
``pairing_module_exists``
    Every R-F2 pairing-table row names source modules that exist on disk (API
    module + every mirror module, resolving ``REPO_MIRROR_ROOTS``).
``route_has_pairing_row``
    Every ``/api/v1/`` view function is mirrored by a pairing-table row.
``pairing_row_has_route``
    Every pairing-table row is reachable from at least one shipped
    ``/api/v1/`` route (no orphan mirror).
``inventory_route_resolves``
    Every *shipped* endpoint-inventory row names a reversible URL.
``inventory_route_has_pairing_row``
    Every *shipped* inventory row's view module has a pairing-table row.
``inventory_urls_are_mounted``
    Every endpoint URL named by a *shipped* inventory row is mounted under
    ``/api/v1/``.

The pairing table is read from ``apps.api.tests.test_import_rule`` (the R-F2
harness is the declared source of truth; the import rule itself is enforced by
that module's own test). ``apps.api`` is not in ``INSTALLED_APPS`` but is an
importable package, so importing the harness data is safe and side-effect free.

Exit code: ``0`` iff every check passes; otherwise ``1`` (a ``FAIL`` line names
the offending row and the reason first).

Usage::

    python src/backend/manage.py verify_parity
    python src/backend/manage.py verify_parity --json

``--json`` emits one machine-readable document (``status``, ``summary``,
``checks[]``) for CI and agents; the plain form emits ``OK|FAIL <check> :: …``
lines plus a summary line. Both forms are byte-identical across runs.
"""

from __future__ import annotations

import ast
import json
import logging
import re
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from django.core.management.base import BaseCommand
from django.urls import (
    URLPattern,
    URLResolver,
    get_resolver,
    resolve,
    reverse,
)

logger = logging.getLogger(__name__)

#: URL prefix mounted in ``config/urls.py`` for the JSON API surface.
API_URL_PREFIX: Final[str] = "api/v1/"

#: Repo-relative path of the R-F2 harness that declares the pairing table.
PAIRING_HARNESS_MODULE: Final[str] = "apps.api.tests.test_import_rule"

#: The harness constants this command consumes (read as literals, never imported).
_HARNESS_CONSTANTS: Final[frozenset[str]] = frozenset(
    {"PAIRING_TABLE", "REPO_MIRROR_ROOTS"}
)

#: API view modules that are **delegated to** by a mounted dispatcher view and
#: therefore have no route of their own. Each entry is
#: ``(delegated_module_path, dispatcher_module_path)``. The delegation is
#: verified, not assumed: the dispatcher's source must import the delegated
#: function and call it, else ``pairing_row_has_route`` fails.
DELEGATING_VIEWS: Final[tuple[tuple[str, str], ...]] = (
    # S2.7 read — ``GET /api/v1/saved-searches/`` is answered by the S3.4
    # ``saved_searches_collection_view`` dispatcher, which imports and calls
    # ``saved_searches_list_view`` for GET (one route cannot hold two views).
    (
        "apps.cabinet.views.api.saved_searches",
        "apps.cabinet.views.api.saved_search_writes",
    ),
)
#: Placeholder argument used for every ``<int:…>`` converter while reversing.
#: A literal id is enough — the check asserts reversibility, not row existence,
#: so no database is consulted.
SAMPLE_INT_ARG: Final[int] = 1

#: Inventory status tokens (``docs/01-spec/api-surface.md`` *Status* legend)
#: that promise the endpoint is live and must therefore reverse.
SHIPPED_STATUS_TOKENS: Final[tuple[str, ...]] = ("shipped",)

#: One absolute ``/api/v1/`` URL token inside an inventory *Endpoint* cell.#: A comma inside a brace group is expanded by :func:`_expand_braces`; a
#: trailing separator is trimmed by :func:`endpoint_paths`.
_URL_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"/api/v1/[A-Za-z0-9_\-/{}.,]*")

#: A path converter inside a route string: ``<int:ad_id>``, ``<slug:x>``.
_CONVERTER_RE: Final[re.Pattern[str]] = re.compile(r"<[^<>/]+>")

#: A placeholder like ``{id}``/``{pk}`` inside an inventory URL template.
_PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(r"\{[^}]*\}")

#: One brace group that lists alternatives: ``{approve,reject,ban}``.
_BRACE_GROUP_RE: Final[re.Pattern[str]] = re.compile(r"\{([^{}]*,[^{}]*)\}")


class CheckName(StrEnum):
    """Stable identifiers of every parity check the command performs."""

    ROUTE_REVERSIBLE = "route_reversible"
    PAIRING_MODULE_EXISTS = "pairing_module_exists"
    ROUTE_HAS_PAIRING_ROW = "route_has_pairing_row"
    PAIRING_ROW_HAS_ROUTE = "pairing_row_has_route"
    INVENTORY_ROUTE_RESOLVES = "inventory_route_resolves"
    INVENTORY_ROUTE_HAS_PAIRING_ROW = "inventory_route_has_pairing_row"
    INVENTORY_URLS_ARE_MOUNTED = "inventory_urls_are_mounted"


class CheckStatus(StrEnum):
    """Verdict tokens of a single check (stable ASCII, machine-readable)."""

    OK = "OK"
    FAIL = "FAIL"


@dataclass(frozen=True)
class InventoryRow:
    """One endpoint-inventory row extracted from ``api-surface.md``.

    ``actions`` is the plan's *Action* cell; ``endpoint`` is the raw
    *Endpoint · Method* cell; ``status`` is the raw *Status* cell. See
    :func:`shipped_inventory` for how the status decides shippedness.
    """

    number: int
    action: str
    endpoint: str
    status: str


@dataclass(frozen=True)
class ApiRoute:
    """One route of the ``/api/v1/`` URLconf."""

    name: str
    path: str
    view_module: str


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one named check, ready for the text or JSON report."""

    name: CheckName
    ok: bool
    detail: str
    failures: tuple[str, ...] = ()

    @property
    def status(self) -> CheckStatus:
        """Return the stable verdict token of this check."""
        return CheckStatus.OK if self.ok else CheckStatus.FAIL


# ---------------------------------------------------------------------------
# Dynamic enumeration
# ---------------------------------------------------------------------------


def collect_api_routes() -> list[ApiRoute]:
    """Return every shipped route mounted under the ``api/v1/`` prefix.

    Walks the live resolver (no static string list), so a route added or
    removed by any app is reflected here without touching this command. Both
    the route string (for the reversibility comparison) and the namespace chain
    (for ``reverse``) are captured from the resolver itself.
    """
    routes: list[ApiRoute] = []
    _walk_patterns(get_resolver().url_patterns, "", (), routes)
    routes.sort(key=lambda route: (route.path, route.name))
    return routes


def _walk_patterns(
    patterns: list[URLPattern | URLResolver],
    prefix: str,
    namespaces: tuple[str, ...],
    sink: list[ApiRoute],
) -> None:
    """Recurse into ``patterns`` under ``prefix``, collecting ``/api/v1/`` routes.

    ``namespaces`` is the chain built from every enclosing ``URLResolver``
    (Django's ``app_name``/``namespace`` pair) — exactly what ``reverse``
    expects. A subtree whose accumulated prefix can no longer become
    ``/api/v1/…`` is skipped, so the walk never descends into the HTML
    namespaces; a resolver included at an empty prefix keeps the parent prefix.
    """
    for pattern in patterns:
        fragment = str(getattr(pattern, "pattern", ""))
        full_prefix = f"{prefix}{fragment}"
        if isinstance(pattern, URLResolver):
            if not _prefix_could_match(full_prefix):
                continue
            nested = (
                (*namespaces, pattern.namespace)
                if pattern.namespace
                else namespaces
            )
            _walk_patterns(pattern.url_patterns, full_prefix, nested, sink)
            continue
        if not _prefix_could_match(full_prefix):
            continue
        if not (full_prefix + "/").startswith(API_URL_PREFIX):
            # e.g. the bare ``api/`` prefix segment itself.
            continue
        route_string = str(getattr(pattern.pattern, "_route", fragment))
        sink.append(
            ApiRoute(
                name=":".join((*namespaces, pattern.name or "")),
                path=f"{prefix}{route_string}",
                view_module=getattr(pattern.callback, "__module__", ""),
            )
        )


def _prefix_could_match(prefix: str) -> bool:
    """Return True when ``prefix`` is a prefix of (or extends) ``api/v1/``."""
    return API_URL_PREFIX.startswith(prefix) or prefix.startswith(API_URL_PREFIX)




def _reverse_path(route: ApiRoute) -> str:
    """Reverse a route, passing a sample id only when its pattern needs one."""
    if "<int:" in route.path:
        path = reverse(route.name, args=[SAMPLE_INT_ARG])
    else:
        path = reverse(route.name)
    return "/" + path.lstrip("/")


# ---------------------------------------------------------------------------
# Declared pairing table + inventory
# ---------------------------------------------------------------------------


def load_pairing_table() -> list[tuple[str, str | tuple[str, ...]]]:
    """Return the R-F2 pairing table (API module, mirror module(s)).

    The harness is **read**, not imported: ``apps/api/tests`` is not shipped in
    the runtime image and test packages must not be imported by production
    code. The literal assignments are parsed from the module source, so the
    harness stays the single declared source of truth.
    """
    literals = _harness_literals()
    raw = literals.get("PAIRING_TABLE", [])
    table: list[tuple[str, str | tuple[str, ...]]] = []
    for entry in raw:
        api_module, mirror_entry = entry
        table.append((str(api_module), _mirror_value(mirror_entry)))
    return table


def load_mirror_roots() -> tuple[tuple[str, str], ...]:
    """Return the ``REPO_MIRROR_ROOTS`` declared by the R-F2 harness."""
    raw = _harness_literals().get("REPO_MIRROR_ROOTS", ())
    roots: list[tuple[str, str]] = []
    for entry in raw:
        prefix, repo_root = entry
        roots.append((str(prefix), str(repo_root)))
    return tuple(roots)


def _mirror_value(entry: Any) -> str | tuple[str, ...]:
    """Normalize one pairing row's mirror cell to ``str`` or ``tuple[str, …]``."""
    if isinstance(entry, str):
        return entry
    return tuple(str(item) for item in entry)


def _harness_literals() -> dict[str, Any]:
    """Return the literal module-level assignments of the R-F2 harness.

    Only ``ast.literal_eval``-able values are read, which is exactly what the
    pairing table and the mirror roots are; anything else is skipped. Both the
    annotated (``X: T = …``) and plain (``X = …``) assignment forms are read.
    """
    source_path = (_backend_root() / Path(*PAIRING_HARNESS_MODULE.split("."))).with_suffix(
        ".py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    literals: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        else:
            continue
        if not isinstance(target, ast.Name) or value is None:
            continue
        if target.id not in _HARNESS_CONSTANTS:
            continue
        try:
            literals[target.id] = ast.literal_eval(value)
        except ValueError:
            logger.warning("Harness constant %s is not a literal", target.id)
    return literals


def _stack_prefixes() -> tuple[list[Path], list[Path]]:
    """Return the file-system roots the command may search, most-specific first.

    * ``import_roots`` — directories from which ``apps.…`` resolves as an
      import path. The module's own location gives ``src/backend`` in the
      repository; ``sys.path`` adds the container's ``/app/src`` and
      ``/app/src/backend`` entries (this module runs on every entry point,
      with or without a container's working directory).
    * ``repo_roots`` — the repository root candidate(s), used for the tracked
      ``docs/`` tree (the deployed image may not carry ``docs/`` at all).
    """
    here = Path(__file__).resolve()
    # ``…/apps/core/management/commands/verify_parity.py`` → backend root.
    backend_root = here.parents[3]
    import_roots: list[Path] = [backend_root]
    for entry in sys.path:
        if not entry:
            continue
        candidate = Path(entry)
        if candidate not in import_roots:
            import_roots.append(candidate)
    repo_roots: list[Path] = [backend_root.parent.parent, backend_root.parent]
    for entry in import_roots[1:]:
        repo_roots.extend([entry, entry.parent, entry.parent.parent])
    return import_roots, repo_roots


def _backend_root() -> Path:
    """Return the first root from which the ``apps`` package resolves."""
    import_roots, _ = _stack_prefixes()
    for root in import_roots:
        if (root / "apps").is_dir():
            return root
    return import_roots[0]


def _repo_root() -> Path:
    """Return the first root that holds the tracked ``docs/01-spec`` tree."""
    _, repo_roots = _stack_prefixes()
    for root in repo_roots:
        if (root / "docs" / "01-spec").is_dir():
            return root
    return repo_roots[0]


def source_path_for(
    dotted_module_path: str, mirror_roots: tuple[tuple[str, str], ...]
) -> Path:
    """Map a dotted module path to its ``.py`` file on disk.

    Mirrors ``test_import_rule._source_path_for``: a path matching a
    ``REPO_MIRROR_ROOTS`` prefix resolves under that repo-relative root once
    the root's last segment is dropped from the dotted path.
    """
    for prefix, repo_root in mirror_roots:
        if dotted_module_path.startswith(prefix):
            base = (_repo_root() / repo_root).parent
            return base.joinpath(*dotted_module_path.split(".")).with_suffix(".py")
    return _backend_root().joinpath(*dotted_module_path.split(".")).with_suffix(".py")


def module_exists(
    dotted_module_path: str, mirror_roots: tuple[tuple[str, str], ...]
) -> bool:
    """Return True when *dotted_module_path* resolves to a source file."""
    return source_path_for(dotted_module_path, mirror_roots).is_file()



def parse_inventory(markdown: str) -> list[InventoryRow]:
    """Parse the endpoint-inventory table out of ``api-surface.md``.

    The table starts at the ``| # | Action | … | Status |`` header and ends at
    the first line that is not a table row. Fenced code blocks are skipped so
    a doc example can never be mistaken for an inventory row.
    """
    rows: list[InventoryRow] = []
    in_table = False
    in_fence = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped.startswith("|"):
            if in_table:
                break
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not in_table:
            in_table = cells and cells[0] == "#" and cells[-1] == "Status"
            continue
        if not cells[0].isdigit():
            # The markdown separator row (``|---|``) and anything else odd.
            continue
        rows.append(
            InventoryRow(
                number=int(cells[0]),
                action=cells[1],
                endpoint=cells[3],
                status=cells[-1],
            )
        )
    return rows


def inventory_markdown() -> str:
    """Return the raw ``api-surface.md`` text (the declared inventory)."""
    return (_repo_root() / "docs" / "01-spec" / "api-surface.md").read_text(
        encoding="utf-8"
    )


def is_shipped(row: InventoryRow) -> bool:
    """Return True when the row's status cell promises a live endpoint."""
    lowered = row.status.lower()
    return any(token in lowered for token in SHIPPED_STATUS_TOKENS)


def shipped_inventory(markdown: str) -> list[InventoryRow]:
    """Return only the inventory rows marked *shipped*."""
    return [row for row in parse_inventory(markdown) if is_shipped(row)]


def endpoint_paths(endpoint_cell: str) -> list[str]:
    """Return the absolute URL paths named by an inventory *Endpoint* cell.

    Handles ``GET /api/v1/ads/{id}/edit/`` and the brace-grouped
    ``POST /api/v1/moderation/{approve,reject,ban}/{id}/`` form; a row naming
    no URL (a stance) yields an empty list.
    """
    paths: list[str] = []
    for raw in _URL_TOKEN_RE.findall(endpoint_cell):
        token = raw.rstrip(".,")
        if token:
            paths.extend(_expand_braces(token))
    return paths


def _expand_braces(path: str) -> list[str]:
    """Expand one brace group of a URL template (``{a,b}`` → ``a``, ``b``)."""
    match = _BRACE_GROUP_RE.search(path)
    if match is None:
        return [path]
    head, tail = path[: match.start()], path[match.end() :]
    expanded: list[str] = []
    for option in match.group(1).split(","):
        expanded.extend(_expand_braces(f"{head}{option}{tail}"))
    return expanded


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_route_reversible(routes: list[ApiRoute]) -> CheckResult:
    """Every ``/api/v1/`` route must reverse and resolve back to itself.

    For each mounted route the name is reversed to a concrete URL and that URL
    is resolved again; the round trip must land on the same route name and a
    ``/api/v1/`` path. This proves the name, the namespace chain and the
    pattern agree — a renamed route or a broken include fails loudly.
    """
    failures: list[str] = []
    for route in routes:
        try:
            reversed_path = _reverse_path(route)
            match = resolve(reversed_path)
        except Exception as error:  # noqa: BLE001 — any reverse error is a failure
            failures.append(f"{route.path} ({route.name}): reverse failed — {error}")
            continue
        resolved_name = ":".join(
            [*match.namespaces, match.url_name]
            if match.url_name
            else list(match.namespaces)
        )
        if resolved_name != route.name:
            failures.append(
                f"{route.name}: reversed to {reversed_path!r}, which resolves "
                f"to {resolved_name!r}"
            )
        elif not reversed_path.lstrip("/").startswith(API_URL_PREFIX):
            failures.append(
                f"{route.name}: reversed to {reversed_path!r}, outside "
                f"{API_URL_PREFIX}"
            )
    return CheckResult(
        name=CheckName.ROUTE_REVERSIBLE,
        ok=not failures,
        detail=f"{len(routes)} route(s) reversed and re-resolved",
        failures=tuple(failures),
    )




def check_pairing_module_exists(
    pairing: list[tuple[str, str | tuple[str, ...]]],
    mirror_roots: tuple[tuple[str, str], ...],
) -> CheckResult:
    """Every pairing row must name source modules that exist."""
    failures: list[str] = []
    for api_module, mirror_entry in pairing:
        mirrors = (mirror_entry,) if isinstance(mirror_entry, str) else mirror_entry
        for module in (api_module, *mirrors):
            if not module_exists(module, mirror_roots):
                failures.append(f"{api_module}: module {module} does not exist")
    return CheckResult(
        name=CheckName.PAIRING_MODULE_EXISTS,
        ok=not failures,
        detail=f"{len(pairing)} pairing row(s) resolved",
        failures=tuple(sorted(set(failures))),
    )


def check_route_has_pairing_row(
    routes: list[ApiRoute],
    pairing: list[tuple[str, str | tuple[str, ...]]],
) -> CheckResult:
    """Every ``/api/v1/`` view must be mirrored by a pairing row."""
    paired = {api_module for api_module, _ in pairing}
    failures = [
        f"{route.path} ({route.name}): view module {route.view_module} has no "
        "pairing row"
        for route in routes
        if route.view_module not in paired
    ]
    return CheckResult(
        name=CheckName.ROUTE_HAS_PAIRING_ROW,
        ok=not failures,
        detail=f"{len(routes)} route(s) matched against {len(paired)} row(s)",
        failures=tuple(failures),
    )


def check_pairing_row_has_route(
    routes: list[ApiRoute],
    pairing: list[tuple[str, str | tuple[str, ...]]],
    delegating: tuple[tuple[str, str], ...] = DELEGATING_VIEWS,
) -> CheckResult:
    """Every pairing row must be reachable from a shipped route.

    A row is reachable when its module hosts a mounted view, or when a mounted
    **dispatcher** module imports and calls the row's view module (the
    one-URL-two-views case). A declared delegation that no dispatcher actually
    performs is a failure, so the allowance cannot rot into a silencer.
    """
    routed = {route.view_module for route in routes}
    delegated: dict[str, list[ApiRoute]] = {}
    for delegated_module, dispatcher_module in delegating:
        for route in routes:
            if route.view_module == dispatcher_module and _calls_module(
                dispatcher_module, delegated_module
            ):
                delegated.setdefault(delegated_module, []).append(route)

    failures: list[str] = []
    for api_module, _ in pairing:
        if api_module in routed:
            continue
        if delegated.get(api_module):
            continue
        if any(api_module == entry[0] for entry in delegating):
            failures.append(
                f"{api_module}: declared delegating view has no mounted "
                "dispatcher that calls it"
            )
        else:
            failures.append(f"{api_module}: pairing row has no /api/v1/ route")
    return CheckResult(
        name=CheckName.PAIRING_ROW_HAS_ROUTE,
        ok=not failures,
        detail=(
            f"{len(pairing)} row(s) matched against {len(routed)} view module(s) "
            f"and {len(delegated)} delegation(s)"
        ),
        failures=tuple(failures),
    )


def _calls_module(dispatcher_module: str, callee_module: str) -> bool:
    """Return True when *dispatcher_module* imports from *callee_module*.

    The check is syntactic (source read, no imports executed): an
    ``from <callee_module> import …`` or ``import <callee_module>`` statement
    is the delegation evidence. A module that names the callee only in a
    docstring does not count.
    """
    source_path = (_backend_root() / Path(*dispatcher_module.split("."))).with_suffix(
        ".py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == callee_module:
            return True
        if isinstance(node, ast.Import) and any(
            alias.name == callee_module for alias in node.names
        ):
            return True
    return False



def _route_for_path(path: str, routes: list[ApiRoute]) -> ApiRoute | None:
    """Return the mounted route whose pattern equals an inventory URL template.

    Both sides are compared in route-string form: absolute (``/api/v1/…``) with
    ``{id}``-style placeholders mapped onto Django's ``<int:…>`` converter.
    """
    normalized = _PLACEHOLDER_RE.sub("<int:ad_id>", path.lstrip("/"))
    if not normalized.endswith("/"):
        normalized += "/"
    for route in routes:
        if route.path == normalized:
            return route
    return None


def check_inventory_route_resolves(
    rows: list[InventoryRow], routes: list[ApiRoute]
) -> CheckResult:
    """Every *shipped* inventory row must name a reversible URL."""
    failures: list[str] = []
    checked = 0
    for row in rows:
        for path in endpoint_paths(row.endpoint):
            checked += 1
            if _route_for_path(path, routes) is None:
                failures.append(
                    f"row #{row.number} ({row.action}): {path} is not a mounted "
                    "/api/v1/ route"
                )
    return CheckResult(
        name=CheckName.INVENTORY_ROUTE_RESOLVES,
        ok=not failures,
        detail=f"{checked} endpoint URL(s) from {len(rows)} shipped row(s)",
        failures=tuple(failures),
    )


def check_inventory_route_has_pairing_row(
    rows: list[InventoryRow], routes: list[ApiRoute], paired_modules: set[str]
) -> CheckResult:
    """Every *shipped* inventory row's view must have a pairing row.

    A row whose URL does not resolve is reported by
    ``inventory_route_resolves`` instead, so it is skipped here rather than
    double-counted.
    """
    failures: list[str] = []
    for row in rows:
        for path in endpoint_paths(row.endpoint):
            route = _route_for_path(path, routes)
            if route is None:
                continue
            if route.view_module not in paired_modules:
                failures.append(
                    f"row #{row.number} ({row.action}): {path} view module "
                    f"{route.view_module} has no pairing row"
                )
    return CheckResult(
        name=CheckName.INVENTORY_ROUTE_HAS_PAIRING_ROW,
        ok=not failures,
        detail=f"{len(rows)} shipped row(s) checked",
        failures=tuple(sorted(set(failures))),
    )


def check_inventory_urls_are_mounted(
    rows: list[InventoryRow], routes: list[ApiRoute]
) -> CheckResult:
    """Every *shipped* endpoint URL must resolve to a mounted route.

    Complements ``inventory_route_resolves`` by asserting the resolved route is
    a real ``/api/v1/`` entry (never a route from another namespace re-used by
    accident). Unresolvable templates are reported by the former.
    """
    failures: list[str] = []
    for row in rows:
        for path in endpoint_paths(row.endpoint):
            route = _route_for_path(path, routes)
            if route is None:
                continue
            if not route.path.startswith(API_URL_PREFIX):
                failures.append(
                    f"row #{row.number} ({row.action}): {path} resolved to "
                    f"{route.path}, outside {API_URL_PREFIX}"
                )
    return CheckResult(
        name=CheckName.INVENTORY_URLS_ARE_MOUNTED,
        ok=not failures,
        detail=f"{len(rows)} shipped row(s) carry an /api/v1/ URL",
        failures=tuple(sorted(set(failures))),
    )


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def run_checks(
    *,
    routes: list[ApiRoute],
    pairing: list[tuple[str, str | tuple[str, ...]]],
    mirror_roots: tuple[tuple[str, str], ...],
    inventory: list[InventoryRow],
) -> list[CheckResult]:
    """Run every parity check in a fixed, deterministic order."""
    paired_modules = {api_module for api_module, _ in pairing}
    return [
        check_route_reversible(routes),
        check_pairing_module_exists(pairing, mirror_roots),
        check_route_has_pairing_row(routes, pairing),
        check_pairing_row_has_route(routes, pairing),
        check_inventory_route_resolves(inventory, routes),
        check_inventory_route_has_pairing_row(inventory, routes, paired_modules),
        check_inventory_urls_are_mounted(inventory, routes),
    ]


def build_report(
    results: list[CheckResult],
    routes: list[ApiRoute],
    pairing: list[tuple[str, str | tuple[str, ...]]],
    inventory: list[InventoryRow],
) -> dict[str, Any]:
    """Assemble the machine-readable report document."""
    failed = [result for result in results if not result.ok]
    families = sorted({route.name.split(":", 1)[0] for route in routes})
    return {
        "command": "verify_parity",
        "status": CheckStatus.FAIL if failed else CheckStatus.OK,
        "summary": {
            "api_routes": len(routes),
            "namespaces": families,
            "pairing_rows": len(pairing),
            "inventory_rows": len(inventory),
            "checks": len(results),
            "passed": len(results) - len(failed),
            "failed": len(failed),
        },
        "checks": [
            {
                "name": result.name,
                "status": result.status,
                "detail": result.detail,
                "failures": list(result.failures),
            }
            for result in results
        ],
    }


class Command(BaseCommand):
    """Audit the declared rule-18 API-parity claims without touching the DB."""

    help = (
        "Read-only rule-18 parity audit of /api/v1/: route reversibility, the "
        "R-F2 pairing table, and the endpoint inventory. Exit 1 on any gap."
    )

    def add_arguments(self, parser) -> None:
        """Register the ``--json`` machine-readable output flag."""
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            default=False,
            help="Emit one machine-readable JSON report (for CI and agents).",
        )

    def handle(self, *args, **options) -> None:
        """Run every check, print the report, and exit non-zero on any FAIL."""
        as_json: bool = options["as_json"]

        routes = collect_api_routes()
        pairing = load_pairing_table()
        mirror_roots = load_mirror_roots()
        inventory = shipped_inventory(inventory_markdown())

        results = run_checks(
            routes=routes,
            pairing=pairing,
            mirror_roots=mirror_roots,
            inventory=inventory,
        )
        report = build_report(results, routes, pairing, inventory)

        if as_json:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        else:
            self._write_text_report(results, report)

        if report["status"] == CheckStatus.FAIL:
            logger.error(
                "verify_parity: %d of %d checks failed",
                report["summary"]["failed"],
                report["summary"]["checks"],
            )
            sys.exit(1)

    def _write_text_report(
        self, results: list[CheckResult], report: dict[str, Any]
    ) -> None:
        """Write the deterministic ``OK|FAIL <check> :: detail`` report."""
        for result in results:
            self.stdout.write(f"{result.status} {result.name} :: {result.detail}")
            for failure in result.failures:
                self.stdout.write(f"    - {failure}")
        summary = report["summary"]
        self.stdout.write(
            "SUMMARY "
            f"status={report['status']} checks={summary['checks']} "
            f"passed={summary['passed']} failed={summary['failed']} "
            f"routes={summary['api_routes']} "
            f"namespaces={','.join(summary['namespaces'])} "
            f"pairing_rows={summary['pairing_rows']} "
            f"inventory_rows={summary['inventory_rows']}"
        )
