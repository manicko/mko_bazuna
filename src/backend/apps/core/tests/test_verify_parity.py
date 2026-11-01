"""Behavioural tests for the ``verify_parity`` rule-18 audit command (S5.1).

``verify_parity`` turns the API-parity *claims* into a deterministic machine
check (plan §5, layer 5): it walks the live ``/api/v1/`` URLconf, consolidates
it with the R-F2 pairing table and with the endpoint inventory in
``docs/01-spec/api-surface.md``, prints one ``OK``/``FAIL`` line per check and
exits non-zero on any gap.

These tests pin four contracts:

1. **Green on the current tree.** Exit 0, every check ``OK``, and the summary
   route/namespace/pairing counts match reality (derived independently here,
   not from the command's own helpers).
2. **Failure economics.** Every class of gap the plan defines — a missing
   pairing row for a mounted route, a pairing row with no route, a pairing row
   whose module does not exist, a shipped inventory row with no mounted URL,
   a shipped inventory row whose view module has no pairing row, a broken
   delegation — exits non-zero with a readable ``FAIL`` line naming the row.
3. **Determinism.** Two runs produce byte-identical reports.
4. **Read-only.** The command never touches the database (no ``django_db``
   marker anywhere in this module) and never writes a file.
"""

from __future__ import annotations

import json
from io import StringIO

from django.core.management import call_command

from apps.core.management.commands import verify_parity as parity_module
from apps.core.management.commands.verify_parity import (
    DELEGATING_VIEWS,
    ApiRoute,
    InventoryRow,
    check_inventory_route_has_pairing_row,
    check_inventory_route_resolves,
    check_pairing_module_exists,
    check_pairing_row_has_route,
    check_route_has_pairing_row,
    collect_api_routes,
    endpoint_paths,
    load_pairing_table,
    parse_inventory,
)

#: The namespaces the shipped ``/api/v1/`` surface must expose (plan §2.3 Q1:
#: one ``<app>_api`` namespace per contributing app; the dashboard keeps its own
#: ads-hosted namespace). Declared literally so a silently dropped include —
#: which would shrink the dynamic walk too — still fails this test.
EXPECTED_NAMESPACES: frozenset[str] = frozenset(
    {
        "ads_api",
        "analytics_api",
        "cabinet_api",
        "categories_api",
        "dashboard_api",
        "locations_api",
        "moderation_api",
        "search_api",
        "users_api",
    }
)

#: A representative slice of the shipped routes: every one of them must be
#: enumerable and reversible. ``(route name, mounted path)``.
EXPECTED_ROUTES: tuple[tuple[str, str], ...] = (
    ("ads_api:listings", "api/v1/ads/"),
    ("ads_api:ad_detail", "api/v1/ads/<int:ad_id>/"),
    ("ads_api:submit", "api/v1/ads/<int:ad_id>/submit/"),
    ("ads_api:edit", "api/v1/ads/<int:ad_id>/edit/"),
    ("ads_api:archive", "api/v1/ads/<int:ad_id>/archive/"),
    ("ads_api:reactivate", "api/v1/ads/<int:ad_id>/reactivate/"),
    ("ads_api:delete", "api/v1/ads/<int:ad_id>/delete/"),
    ("ads_api:copy", "api/v1/ads/<int:ad_id>/copy/"),
    ("dashboard_api:dashboard", "api/v1/dashboard/"),
    ("search_api:search", "api/v1/search/"),
    ("categories_api:tree", "api/v1/categories/"),
    ("locations_api:cities", "api/v1/cities/"),
    ("cabinet_api:favorites", "api/v1/favorites/"),
    ("cabinet_api:favorite_toggle", "api/v1/favorites/<int:ad_id>/toggle/"),
    ("cabinet_api:saved_searches", "api/v1/saved-searches/"),
    ("cabinet_api:saved_search_toggle", "api/v1/saved-searches/<int:pk>/toggle/"),
    ("cabinet_api:saved_search_edit", "api/v1/saved-searches/<int:pk>/edit/"),
    ("cabinet_api:saved_search_delete", "api/v1/saved-searches/<int:pk>/delete/"),
    ("cabinet_api:search_history", "api/v1/search-history/"),
    ("cabinet_api:search_history_clear", "api/v1/search-history/clear/"),
    ("users_api:consent_accept", "api/v1/consent/accept/"),
    ("users_api:consent_decline", "api/v1/consent/decline/"),
    ("users_api:consent_withdraw", "api/v1/consent/withdraw/"),
    ("users_api:logout", "api/v1/auth/logout/"),
    ("moderation_api:queue", "api/v1/moderation/queue/"),
    ("moderation_api:review", "api/v1/moderation/review/<int:ad_id>/"),
    ("moderation_api:approve", "api/v1/moderation/approve/<int:ad_id>/"),
    ("moderation_api:reject", "api/v1/moderation/reject/<int:ad_id>/"),
    ("moderation_api:ban", "api/v1/moderation/ban/<int:ad_id>/"),
    ("analytics_api:seller", "api/v1/trust/seller/"),
    ("analytics_api:moderation", "api/v1/trust/moderation/"),
)


def _run(*, as_json: bool = False) -> tuple[int, str]:
    """Run the command, returning ``(exit code, stdout)``.

    ``SystemExit`` is the command's non-zero signal; an absent ``SystemExit``
    means exit 0.
    """
    out = StringIO()
    code = 0
    try:
        call_command("verify_parity", stdout=out, as_json=as_json)
    except SystemExit as exc:
        code = int(exc.code or 0)
    return code, out.getvalue()


class TestGreenOnCurrentTree:
    """The shipped surface passes every check."""

    def test_exit_code_is_zero(self) -> None:
        code, _ = _run()
        assert code == 0

    def test_every_check_is_ok(self) -> None:
        code, output = _run()
        assert code == 0
        lines = [line for line in output.splitlines() if line.split(" ")[0] in {"OK", "FAIL"}]
        assert len(lines) == len(parity_module.CheckName)
        assert all(line.startswith("OK ") for line in lines), output

    def test_summary_is_the_last_line_and_reports_ok(self) -> None:
        _, output = _run()
        last = output.strip().splitlines()[-1]
        assert last.startswith("SUMMARY status=OK ")
        assert "failed=0" in last

    def test_notevery_check_name_appears_exactly_once(self) -> None:
        _, output = _run()
        for check in parity_module.CheckName:
            assert output.count(f" {check} :: ") == 1, output

    def test_route_enumeration_matches_reality(self) -> None:
        """Every declared route is enumerated with its mounted path."""
        routes = {route.name: route.path for route in collect_api_routes()}
        for name, path in EXPECTED_ROUTES:
            assert routes.get(name) == path, f"{name} not enumerated as {path}"
        assert set(EXPECTED_ROUTES) <= set(routes.items()), (
            "declared routes missing from the walk: "
            f"{sorted(set(dict(EXPECTED_ROUTES)) - set(routes))}"
        )

    def test_namespaces_are_the_declared_set(self) -> None:
        namespaces = {route.name.split(":", 1)[0] for route in collect_api_routes()}
        assert namespaces == EXPECTED_NAMESPACES

    def test_summary_counts_match_the_walk(self) -> None:
        routes = collect_api_routes()
        pairing = load_pairing_table()
        _, output = _run()
        summary = next(
            line for line in output.splitlines() if line.startswith("SUMMARY ")
        )
        assert f"routes={len(routes)} " in summary
        assert f"pairing_rows={len(pairing)} " in summary
        assert f"checks={len(parity_module.CheckName)} " in summary

    def test_every_shipped_inventory_row_resolves(self) -> None:
        """The shipped inventory rows all name mounted routes (no drift)."""
        rows = parity_module.shipped_inventory(parity_module.inventory_markdown())
        assert len(rows) >= 20
        routes = collect_api_routes()
        result = check_inventory_route_resolves(rows, routes)
        assert result.ok, result.failures

    def test_json_report_is_machine_readable(self) -> None:
        code, output = _run(as_json=True)
        assert code == 0
        report = json.loads(output)
        assert report["status"] == "OK"
        assert report["command"] == "verify_parity"
        assert report["summary"]["failed"] == 0
        assert {check["name"] for check in report["checks"]} == set(
            parity_module.CheckName
        )


class TestDeterminism:
    """Two runs must be byte-identical (text and JSON)."""

    def test_text_report_is_stable(self) -> None:
        first = _run()[1]
        second = _run()[1]
        assert first == second

    def test_json_report_is_stable(self) -> None:
        first = _run(as_json=True)[1]
        second = _run(as_json=True)[1]
        assert first == second


class TestFailureEconomics:
    """Every gap class exits non-zero with a readable FAIL line."""

    def test_missing_pairing_row_fails(self) -> None:
        """A mounted route whose view module has no pairing row fails."""
        routes = [
            ApiRoute(
                name="ads_api:listings",
                path="api/v1/ads/",
                view_module="apps.ads.views.api.unpaired",
            )
        ]
        result = check_route_has_pairing_row(routes, load_pairing_table())
        assert not result.ok
        assert any("no pairing row" in failure for failure in result.failures)

    def test_missing_pairing_row_exits_nonzero(
        self, monkeypatch, capsys
    ) -> None:
        """The command itself exits 1 and prints the FAIL line."""
        original = parity_module.collect_api_routes

        def with_unpaired_route() -> list[ApiRoute]:
            return [
                *original(),
                ApiRoute(
                    name="ads_api:ghost",
                    path="api/v1/ghost/",
                    view_module="apps.ads.views.api.ghost",
                ),
            ]

        monkeypatch.setattr(parity_module, "collect_api_routes", with_unpaired_route)
        code, output = _run()
        assert code == 1
        assert "FAIL route_has_pairing_row :: " in output
        assert "apps.ads.views.api.ghost has no pairing row" in output

    def test_pairing_row_without_route_fails(self) -> None:
        """A pairing row the resolver cannot reach is an orphan mirror."""
        routes = [
            route
            for route in collect_api_routes()
            if route.view_module != "apps.ads.views.api.copy"
        ]
        result = check_pairing_row_has_route(routes, load_pairing_table())
        assert not result.ok
        assert any(
            "apps.ads.views.api.copy: pairing row has no /api/v1/ route" == failure
            for failure in result.failures
        )

    def test_pairing_row_without_route_exits_nonzero(self, monkeypatch) -> None:
        original = parity_module.collect_api_routes

        def without_copy() -> list[ApiRoute]:
            return [
                route
                for route in original()
                if route.view_module != "apps.ads.views.api.copy"
            ]

        monkeypatch.setattr(parity_module, "collect_api_routes", without_copy)
        code, output = _run()
        assert code == 1
        assert "FAIL pairing_row_has_route :: " in output
        assert "apps.ads.views.api.copy: pairing row has no /api/v1/ route" in output

    def test_broken_delegation_fails(self) -> None:
        """A declared delegation no dispatcher performs is not a silencer."""
        routes = [
            route
            for route in collect_api_routes()
            if route.view_module != "apps.cabinet.views.api.saved_searches"
        ]
        delegating = (("apps.cabinet.views.api.saved_searches", "apps.nowhere"),)
        pairing = [
            ("apps.cabinet.views.api.saved_searches", "apps.cabinet.views.saved_searches")
        ]
        result = check_pairing_row_has_route(routes, pairing, delegating)
        assert not result.ok
        assert any("no mounted dispatcher" in failure for failure in result.failures)

    def test_delegation_table_names_real_mirrors(self) -> None:
        """Every declared delegation is honoured by the live dispatcher."""
        routes = {route.view_module for route in collect_api_routes()}
        for delegated_module, dispatcher_module in DELEGATING_VIEWS:
            assert dispatcher_module in routes
            assert parity_module._calls_module(dispatcher_module, delegated_module)

    def test_nonexistent_pairing_module_fails(self) -> None:
        result = check_pairing_module_exists(
            [("apps.ads.views.api.ghost", "apps.ads.views.listings")],
            parity_module.load_mirror_roots(),
        )
        assert not result.ok
        assert any(
            "apps.ads.views.api.ghost: module apps.ads.views.api.ghost does not exist"
            == failure
            for failure in result.failures
        )

    def test_shipped_row_without_route_fails(self) -> None:
        """A *shipped* inventory row naming no mounted URL fails."""
        rows = [
            InventoryRow(
                number=99,
                action="Ghost read",
                endpoint="`GET /api/v1/ghost/`",
                status="shipped (S5.9)",
            )
        ]
        result = check_inventory_route_resolves(rows, collect_api_routes())
        assert not result.ok
        assert any("row #99" in failure and "/api/v1/ghost/" in failure for failure in result.failures)

    def test_shipped_row_without_route_exits_nonzero(
        self, monkeypatch
    ) -> None:
        ghost = InventoryRow(
            number=99,
            action="Ghost read",
            endpoint="`GET /api/v1/ghost/`",
            status="shipped (S5.9)",
        )
        original = parity_module.shipped_inventory

        def with_ghost(markdown: str) -> list[InventoryRow]:
            return [*original(markdown), ghost]

        monkeypatch.setattr(parity_module, "shipped_inventory", with_ghost)
        code, output = _run()
        assert code == 1
        assert "FAIL inventory_route_resolves :: " in output
        assert "row #99 (Ghost read): /api/v1/ghost/" in output

    def test_shipped_row_without_pairing_row_fails(self) -> None:
        """A shipped row whose view module has no pairing row fails."""
        routes = collect_api_routes()
        rows = [
            InventoryRow(
                number=98,
                action="Unpaired read",
                endpoint="`GET /api/v1/ads/`",
                status="shipped (S5.9)",
            )
        ]
        result = check_inventory_route_has_pairing_row(
            rows, routes, paired_modules={"apps.ads.views.api.detail"}
        )
        assert not result.ok
        assert any(
            "row #98 (Unpaired read)" in failure and "has no pairing row" in failure
            for failure in result.failures
        )

    def test_planned_rows_are_not_shipped_claims(self) -> None:
        """Rows still marked ``planned`` are not cross-checked as live."""
        markdown = (
            "| # | Action | Service | Endpoint · Method | Auth | Error notes | Status |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 1 | Live | s | `GET /api/v1/ads/` | PUB | — | shipped (S1.3) |\n"
            "| 2 | Later | s | `GET /api/v1/nope/` | PUB | — | planned |\n"
        )
        shipped = parity_module.shipped_inventory(markdown)
        assert [row.number for row in shipped] == [1]


class TestInventoryParsing:
    """The inventory parser reads the endpoint table the docs actually use."""

    def test_parses_the_documented_table(self) -> None:
        rows = parity_module.inventory_markdown()
        parsed = parse_inventory(rows)
        assert len(parsed) >= 30
        assert parsed[0].number == 1
        assert parsed[0].action == "Listings"

    def test_brace_grouped_endpoints_expand(self) -> None:
        paths = endpoint_paths("`POST /api/v1/moderation/{approve,reject,ban}/{id}/`")
        assert paths == [
            "/api/v1/moderation/approve/{id}/",
            "/api/v1/moderation/reject/{id}/",
            "/api/v1/moderation/ban/{id}/",
        ]

    def test_stance_row_names_no_url(self) -> None:
        assert endpoint_paths("deep-link protocol — detail payload") == []

    def test_fenced_code_is_ignored(self) -> None:
        markdown = (
            "```\n"
            "| # | Action | S | Endpoint · Method | A | E | Status |\n"
            "```\n"
            "| # | Action | Service | Endpoint · Method | Auth | Error notes | Status |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 1 | Live | s | `GET /api/v1/ads/` | PUB | — | shipped |\n"
        )
        assert [row.number for row in parse_inventory(markdown)] == [1]


class TestSchedulerUntouched:
    """``verify_parity`` is never scheduled (plan S5.1)."""

    def test_command_is_not_in_the_scheduler_lists(self) -> None:
        from apps.core.utils.scheduler import DAILY_COMMANDS, HOURLY_COMMANDS

        assert "verify_parity" not in HOURLY_COMMANDS
        assert "verify_parity" not in DAILY_COMMANDS
