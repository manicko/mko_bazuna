"""
Management command to run ``EXPLAIN (ANALYZE, BUFFERS)`` on representative
search, listing, and filter queries against the ``ads`` table.

Asserts no sequential scan (Seq Scan) on the ads table at seed scale
(>10k published rows), per docs/99-agent/rules.md:227. References
``PerformanceSLO`` constants (src/benchmark/constants.py) in its
regression-threshold output, satisfying rules.md:228.

Usage::

    python -m manage.py profile_queries
    python -m manage.py profile_queries --query "велосипед" --table ads
    python -m manage.py profile_queries --dry-run

Requires a running PostgreSQL database with seed data (>=10k published ads)
so the Seq-Scan assertion is meaningful. In the dev environment, run
``make up`` first to seed the database.
"""

import logging
import re
from typing import Final

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import F, Q, QuerySet

from apps.ads.models import Ad
from apps.core.enums import AdStatus, LanguageLocale
from benchmark.constants import PerformanceSLO

logger = logging.getLogger(__name__)

# Minimum published-row count for the Seq-Scan assertion to be meaningful
# (seed scale). Below this the planner may legitimately choose a sequential
# scan because the table is too small to benefit from an index.
SEED_SCALE_MIN_ROWS: Final[int] = 10_000


class Command(BaseCommand):
    """Run EXPLAIN (ANALYZE, BUFFERS) on representative ad queries.

    Examines the FTS search, listings, and filter query patterns that mirror
    the production search/listings views (apps.search.views.search and
    apps.ads.services.listings_query). Asserts that the planner never falls
    back to a sequential scan on the ads table when it holds >10k published
    rows (seed scale). If it does, add an index before tuning the query
    (docs/99-agent/rules.md:227).

    The regression-threshold output references ``PerformanceSLO`` constants
    (src/benchmark/constants.py) so the SLO budget is visible alongside the
    plan (docs/99-agent/rules.md:228).
    """

    help = (
        "Run EXPLAIN (ANALYZE, BUFFERS) on representative search/listing/filter "
        "queries and assert no Seq Scan on the ads table at seed scale."
    )

    def add_arguments(self, parser) -> None:
        """Register CLI flags for table selection, search term, and dry-run."""
        parser.add_argument(
            "--table",
            default=Ad._meta.db_table,
            help=(
                "Table to assert no sequential scan against "
                "(default: %(default)s, derived from Ad._meta.db_table)"
            ),
        )
        parser.add_argument(
            "--query",
            default="laptop",
            help="Search term for the FTS EXPLAIN query (default: %(default)s)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Print the SQL that would be explained without executing EXPLAIN.",
        )

    def handle(self, *args, **options) -> None:
        """Execute EXPLAIN on representative queries and assert index usage."""
        table: str = options["table"]
        search_term: str = options["query"]
        dry_run: bool = options["dry_run"]

        # Surface SLO constants in operational output (rules.md:228).
        logger.info(
            "Profiling thresholds — p95 SLO: %dms "
            "(PerformanceSLO.P95_SLO_MS), p99 SLO: %dms "
            "(PerformanceSLO.P99_SLO_MS)",
            int(PerformanceSLO.P95_SLO_MS),
            int(PerformanceSLO.P99_SLO_MS),
        )
        self.stdout.write(
            f"SLO regression thresholds: "
            f"p95={PerformanceSLO.P95_SLO_MS}ms, "
            f"p99={PerformanceSLO.P99_SLO_MS}ms"
        )

        queries = self._build_queries(search_term)

        row_count = Ad.objects.filter(status=AdStatus.PUBLISHED).count()
        logger.info("Published ads in '%s': %d", table, row_count)
        self.stdout.write(f"Published ads: {row_count}")

        if row_count < SEED_SCALE_MIN_ROWS:
            self.stdout.write(
                self.style.WARNING(
                    f"WARNING: only {row_count} published ads — "
                    f"Seq-Scan assertion skipped (need >={SEED_SCALE_MIN_ROWS} "
                    f"for seed-scale profiling). Run 'make up' to seed the dev DB."
                )
            )

        failures: list[str] = []
        for label, queryset in queries:
            self.stdout.write(f"\n── {label} ──")
            explain_output = self._explain(queryset, dry_run)
            self.stdout.write(explain_output)

            if not dry_run and row_count >= SEED_SCALE_MIN_ROWS:
                if self._has_seq_scan(explain_output, table):
                    msg = (
                        f"Seq Scan detected on '{table}' in the '{label}' query — "
                        f"add an index before tuning the query (rules.md:227)."
                    )
                    logger.error(msg)
                    failures.append(msg)

        if failures:
            raise CommandError(
                "Profiling failed — sequential scans detected:\n  "
                + "\n  ".join(failures)
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Profiling complete — no Seq Scan on '{table}' at "
                f"{row_count} rows. p95 SLO={PerformanceSLO.P95_SLO_MS}ms, "
                f"p99 SLO={PerformanceSLO.P99_SLO_MS}ms."
            )
        )

    def _build_queries(self, search_term: str) -> list[tuple[str, QuerySet[Ad]]]:
        """Build representative querysets mirroring the search/listings views.

        Query patterns are derived from:
        - apps.search.views.search — FTS search on the per-language vector
        - apps.ads.services.listings_query — base PUBLISHED filter + sort

        Returns a list of ``(label, queryset)`` pairs so callers can correlate
        each EXPLAIN output with the query it represents.
        """
        vector_field = LanguageLocale.RUSSIAN.fts_vector_field
        fts_config = LanguageLocale.RUSSIAN.fts_config
        search_query = SearchQuery(
            search_term, search_type="websearch", config=fts_config
        )

        base = Ad.objects.filter(
            status=AdStatus.PUBLISHED,
        ).filter(Q(category__isnull=True) | Q(category__is_active=True))

        return [
            (
                "fts_search (websearch)",
                base.annotate(
                    rank=SearchRank(F(vector_field), search_query),
                ).filter(**{vector_field: search_query}),
            ),
            (
                "listing (all published, newest first)",
                base.order_by("-published_at"),
            ),
            (
                "filter_by_city",
                base.filter(city_id=1).order_by("-published_at"),
            ),
            (
                "filter_by_category_subtree",
                base.filter(category_id__in=[1, 2, 3]).order_by("-published_at"),
            ),
            (
                "filter_by_price_range",
                base.filter(
                    price_normalized_eur__gte=100,
                    price_normalized_eur__lte=10000,
                ).order_by("-published_at"),
            ),
            (
                "sort_by_price_asc",
                base.order_by(
                    F("price_normalized_eur").asc(nulls_last=True)
                ),
            ),
        ]

    def _explain(self, queryset: QuerySet[Ad], dry_run: bool) -> str:
        """Run ``EXPLAIN (ANALYZE, BUFFERS)`` via raw SQL on *queryset*.

        Uses ``django.db.connection`` for raw SQL execution (PostgreSQL 18
        specific). The queryset is compiled via ``SQLCompiler.as_sql`` so the
        exact plan mirrors what the ORM sends to the database. When *dry_run*
        is True the compiled SQL is returned without execution.
        """
        compiler = queryset.query.get_compiler(using=queryset.db)
        sql, params = compiler.as_sql()
        if dry_run:
            return f"EXPLAIN (ANALYZE, BUFFERS) {sql}"
        with connection.cursor() as cursor:
            cursor.execute(f"EXPLAIN (ANALYZE, BUFFERS) {sql}", params)
            rows = cursor.fetchall()
        return "\n".join(str(row[0]) for row in rows)

    @staticmethod
    def _has_seq_scan(explain_output: str, table_name: str) -> bool:
        """Return True if EXPLAIN output shows a sequential scan on *table_name*.

        PostgreSQL EXPLAIN ANALYZE output prefixes each plan node with the
        node type, e.g. ``Seq Scan on ads``.  We match ``Seq Scan on
        <table>`` with a regex word boundary so a table named ``ads`` does not
        match ``ads_images``.
        """
        pattern = re.compile(rf"Seq Scan on {re.escape(table_name)}\b")
        return bool(pattern.search(explain_output))
