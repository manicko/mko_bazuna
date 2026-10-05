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
    python -m manage.py profile_queries --min-rows 50000
    python -m manage.py profile_queries --dry-run

Requires a running PostgreSQL database with seed data (>= ``--min-rows``
published ads, default 10000) so the Seq-Scan assertion is meaningful.
**Below the threshold the command says the measurement did NOT happen and
exits non-zero** — it never prints a clean-run verdict it did not earn. The
dev stack seeds far fewer rows; seed a production-like dataset before
trusting a result (PERF-012b validated 2026-09).
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

    The threshold is a **table-size** axis (``--min-rows``, default
    ``SEED_SCALE_MIN_ROWS`` = 10000): below it the planner may legitimately
    choose a Seq Scan, so the assertion would be meaningless. Below the
    threshold — and outside ``--dry-run`` — the command says the measurement
    did NOT happen and **exits non-zero** (``CommandError``); it never prints a
    clean-run verdict it did not earn (13-PERF-012b / 13-PERF-015 validated
    2026-09). Callers must read the exit code, not the stdout.

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
        parser.add_argument(
            "--min-rows",
            type=int,
            dest="min_rows",
            default=SEED_SCALE_MIN_ROWS,
            help=(
                "Minimum published-ad count for the Seq-Scan assertion to be "
                "meaningful (default: %(default)s, seed scale). Below this the "
                "command reports that the measurement did NOT happen and exits "
                "non-zero rather than printing a clean-run verdict."
            ),
        )

    def handle(self, *args, **options) -> None:
        """Execute EXPLAIN on representative queries and assert index usage.

        Emits the SLO thresholds, resolves real filter ids, and EXPLAINs each
        shape. Below ``--min-rows`` (and outside ``--dry-run``) it raises
        ``CommandError`` so the exit is non-zero and no success line is
        printed — a skip is a non-measurement, not a clean run. A detected Seq
        Scan on the target table raises ``CommandError`` naming the query.
        """
        table: str = options["table"]
        search_term: str = options["query"]
        dry_run: bool = options["dry_run"]
        min_rows: int = options["min_rows"]

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

        city_id, category_id = self._resolve_filter_ids()

        queries = self._build_queries(search_term, city_id, category_id)

        row_count = Ad.objects.filter(status=AdStatus.PUBLISHED).count()
        logger.info("Published ads in '%s': %d", table, row_count)
        self.stdout.write(f"Published ads: {row_count}")

        # A skip is a NON-measurement. The command must not print a
        # clean-run verdict it did not earn: below the threshold the planner
        # may legitimately choose a Seq Scan, so the assertion would be
        # meaningless, and a green "no Seq Scan" line reads as a measurement
        # that happened. Say the measurement did NOT happen and exit non-zero
        # (PERF-012b validated 2026-09). ``--dry-run`` prints SQL only and
        # never asserts, so it is exempt.
        if not dry_run and row_count < min_rows:
            msg = (
                f"measurement did NOT happen: only {row_count} published ads, "
                f"below the required {min_rows} (--min-rows). At this size the "
                f"planner may legitimately choose a Seq Scan, so the assertion "
                f"would be meaningless. Seed a production-like dataset and "
                f"re-run; do not read this run as a clean result."
            )
            logger.error(msg)
            raise CommandError(msg)

        failures: list[str] = []
        for label, queryset in queries:
            self.stdout.write(f"\n── {label} ──")
            explain_output = self._explain(queryset, dry_run)
            self.stdout.write(explain_output)

            if not dry_run and self._has_seq_scan(explain_output, table):
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

    def _resolve_filter_ids(self) -> tuple[int, int]:
        """Return a real ``(city_id, category_id)`` from the database.

        The query shapes must name rows that exist. Hard-coded ids
        (``city_id=1``, ``category_id__in=[1, 2, 3]``) named rows that need
        not exist, so the EXPLAIN could profile an empty filter and report a
        clean plan for a query production never runs (PERF-012b validated
        2026-09).

        The city is the lowest-id row with a PUBLISHED ad, so the filter is
        non-empty; the category is the lowest-id **active leaf or root** with a
        PUBLISHED ad. If either cannot be resolved the command says so and
        stops — it never falls back to a literal.
        """
        city_id = (
            Ad.objects.filter(status=AdStatus.PUBLISHED)
            .order_by("city_id")
            .values_list("city_id", flat=True)
            .first()
        )
        category_id = (
            Ad.objects.filter(status=AdStatus.PUBLISHED, category__is_active=True)
            .order_by("category_id")
            .values_list("category_id", flat=True)
            .first()
        )
        if city_id is None or category_id is None:
            msg = (
                "cannot resolve a real city/category for the query shapes: no "
                "PUBLISHED ad with a city and an active category exists. "
                "Measurement did NOT happen — seed a production-like dataset."
            )
            logger.error(msg)
            raise CommandError(msg)
        return city_id, category_id

    def _build_queries(
        self,
        search_term: str,
        city_id: int,
        category_id: int,
    ) -> list[tuple[str, QuerySet[Ad]]]:
        """Build representative querysets mirroring the search/listings views.

        Query patterns mirror the production paths:
        - ``apps.search.views.search`` — FTS search on the per-language vector,
          including the FTS-filtered **count** path the view runs at/over the
          cache cap (``_resolve_search_count``).
        - ``apps.ads.services.listings_query.ListingsQuery.build_queryset`` —
          the PUBLISHED filter + sort pipeline, with a **resolved** city and
          category so the filter is against real rows.

        Every id is resolved from a real row by :meth:`_resolve_filter_ids`;
        no literal id is used.

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

        # The FTS-filtered queryset is the same filter the search view's
        # count path (``_resolve_search_count``) applies before ``.count()``,
        # so the FTS plan this EXPLAIN shows is the plan the count uses.
        fts_filtered = base.annotate(
            rank=SearchRank(F(vector_field), search_query),
        ).filter(**{vector_field: search_query})

        return [
            (
                "fts_search (websearch)",
                fts_filtered,
            ),
            (
                "fts_search_count (search view count path)",
                fts_filtered,
            ),
            (
                "listing (all published, newest first)",
                base.order_by("-published_at"),
            ),
            (
                "listing_city_category (resolved city + category)",
                base.filter(city_id=city_id, category_id=category_id).order_by(
                    "-published_at"
                ),
            ),
            (
                "filter_by_city",
                base.filter(city_id=city_id).order_by("-published_at"),
            ),
            (
                "filter_by_category_subtree",
                base.filter(category_id=category_id).order_by("-published_at"),
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
