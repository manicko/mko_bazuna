"""Behavioural tests for the ``profile_queries`` command (PERF-012b).

``profile_queries`` is the repository's only query-plan tool. It used to
report a **clean run it did not perform**: below ``SEED_SCALE_MIN_ROWS`` it
printed a green "Profiling complete — no Seq Scan" line and exited 0 while
skipping its assertion entirely. A tool that lies about a measurement is worse
than an absent one.

These tests pin the corrected contract:

1. Below the threshold the command **exits non-zero** and its message says the
   measurement did **not** happen. The exit code is the assertion — not a log
   line (the VAL-003 class at the tool level).
2. Above the threshold a clean plan succeeds, and a real Seq Scan is detected
   and fails the command.
3. Every id in ``_build_queries`` is resolved from a real row; no literal id
   remains, and an unresolvable filter stops the command instead of falling
   back to ``city_id=1``.
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command

from apps.core.enums import AdStatus
from apps.core.management.commands import profile_queries as profile_module
from apps.core.management.commands.profile_queries import Command

pytestmark = [pytest.mark.django_db]


def _call(**overrides) -> str:
    """Run the command, returning its stdout; raise through on error."""
    out = StringIO()
    call_command("profile_queries", stdout=out, **overrides)
    return out.getvalue()


class TestSkipIsLoud:
    """A skip must be a non-measurement, not a silently green run."""

    def test_below_threshold_exits_nonzero(self, seller, category, city) -> None:
        """Below ``--min-rows`` the command raises (non-zero exit)."""
        from conftest import create_test_ad

        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        out = StringIO()
        with pytest.raises(CommandError) as exc:
            call_command("profile_queries", stdout=out, min_rows=10_000)
        assert "did NOT happen" in str(exc.value)

    def test_below_threshold_does_not_print_a_clean_verdict(
        self, seller, category, city
    ) -> None:
        """The skip path must not emit the success line (the old lie)."""
        from conftest import create_test_ad

        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        out = StringIO()
        with pytest.raises(CommandError):
            call_command("profile_queries", stdout=out, min_rows=10_000)
        assert "Profiling complete" not in out.getvalue()

    def test_skip_message_names_the_unmet_threshold(
        self, seller, category, city
    ) -> None:
        """The message states the required and actual counts."""
        from conftest import create_test_ad

        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        out = StringIO()
        with pytest.raises(CommandError) as exc:
            call_command("profile_queries", stdout=out, min_rows=10_000)
        message = str(exc.value)
        assert "10000" in message
        assert "1 published ads" in message


class TestAboveThreshold:
    """Above the threshold the assertion is live and the exit code is honest."""

    def test_clean_plan_succeeds(self, seller, category, city) -> None:
        """A plan with no Seq Scan on the target table exits 0."""
        from conftest import create_test_ad

        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        with patch.object(
            Command, "_has_seq_scan", return_value=False
        ):
            output = _call(min_rows=1)
        assert "Profiling complete" in output

    def test_real_seq_scan_fails_the_command(self, seller, category, city) -> None:
        """A detected Seq Scan raises ``CommandError`` naming the query."""
        from conftest import create_test_ad

        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        with patch.object(Command, "_has_seq_scan", return_value=True):
            with pytest.raises(CommandError) as exc:
                _call(min_rows=1)
        assert "Seq Scan detected" in str(exc.value)

    def test_dry_run_is_exempt_from_the_threshold(self, seller, category, city) -> None:
        """``--dry-run`` prints SQL only and never asserts, so it succeeds."""
        from conftest import create_test_ad

        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        output = _call(min_rows=10_000, dry_run=True)
        assert "EXPLAIN" in output


class TestResolvedIds:
    """Every id is resolved from a real row; no literal id remains."""

    def test_build_queries_filters_on_resolved_ids(
        self, seller, category, city
    ) -> None:
        """The city/category filters carry the resolved ids, not literals."""
        from conftest import create_test_ad

        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        command = Command()
        city_id, category_id = command._resolve_filter_ids()
        assert city_id == ad.city_id
        assert category_id == ad.category_id

        # Django compiles filter values as bound parameters, so the resolved
        # ids appear in ``params``, not in the SQL text.
        bound_params: list[object] = []
        for _, queryset in command._build_queries("laptop", city_id, category_id):
            _, params = queryset.query.get_compiler(using="default").as_sql()
            bound_params.extend(params)
        assert city_id in bound_params
        assert category_id in bound_params

    def test_unresolvable_filter_stops_the_command(self) -> None:
        """With no published ad the command reports and stops, never guesses."""
        command = Command()
        with pytest.raises(CommandError) as exc:
            command._resolve_filter_ids()
        assert "cannot resolve" in str(exc.value)

    def test_build_queries_source_has_no_literal_ids(self) -> None:
        """``_build_queries`` must not hard-code ``city_id=1`` / ``[1, 2, 3]``.

        An AST guard so the assertion cannot be met by prose: no ``Compare``
        against a bare integer literal and no list of integer literals in the
        function body. The ids are parameters, resolved by the caller.
        """
        import ast
        from pathlib import Path

        source = Path(profile_module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        func = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_build_queries"
        )
        literal_ints = [
            node.value
            for node in ast.walk(func)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, int)
            and not isinstance(node.value, bool)
        ]
        # The only integer literals allowed in the shapes are the price bounds.
        assert set(literal_ints) <= {100, 10000}, (
            "no literal id may remain in _build_queries; ids are resolved from "
            f"real rows (found integer literals: {sorted(literal_ints)})"
        )
