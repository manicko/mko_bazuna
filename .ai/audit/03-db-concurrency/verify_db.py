"""Phase 03 (Database & Concurrency) runtime verification harness.

READ-ONLY with respect to production code: this script only creates sentinel
rows and removes them in its `cleanup()` block.

Run inside the mko-bazuna-test compose project (tests run only in Docker):

    $dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test ' +
          '-f docker-compose.yml -f docker-compose.test.yml'
    $dc run --rm --no-deps test python /app/.ai/audit/03-db-concurrency/verify_db.py

Sections referenced from .ai/audit/03-db-concurrency/findings.md:
    A   effective CONN_MAX_AGE / OPTIONS / isolation level / max_connections
    B   create_draft_ad IntegrityError backstop (no savepoint)      -> DB-001
    C   record_event swallowing a deferred FK violation              -> DB-002
    C2  record_event swallowing an immediate statement error         -> DB-002
    D   advisory lock: two concurrent sweep attempts                (PASS)
    E   advisory lock visible in pg_locks while held                (PASS)
    F   advisory lock released on ROLLBACK                          (PASS)
    G   concurrent LoginToken claim                                 (PASS)
    H   concurrent create_draft_ad through the real coroutine       (PASS)
    I   connection churn under concurrency                          (PASS)
    J   sweep_drafts vs an in-flight bot dialog                     -> DB-003
    K   delete_sweep vs a concurrent reactivation                    -> DB-006
    L   row lock held by a sweep stalls the whole bot               -> DB-004
    M   sweep_orphaned_media vs an in-flight submit_ad             -> DB-005
    N   immediate-alert writer vs daily send_alerts writer          -> DB-007
    O   copy_ad with a pre-existing DRAFT                          -> DB-009
"""

from __future__ import annotations

import datetime
import os
import sys
import threading
import time
import traceback
import uuid

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

import django  # noqa: E402

django.setup()

import psycopg  # noqa: E402
from django.db import IntegrityError, connection, connections, transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.ads.models import Ad, AdImage  # noqa: E402
from apps.analytics.models import AnalyticsEvent  # noqa: E402
from apps.core.enums import AdStatus, AdvisoryLockId, AnalyticsEventType  # noqa: E402
from apps.core.services.analytics import record_event  # noqa: E402
from apps.core.utils.advisory_lock import advisory_lock  # noqa: E402
from apps.users.models import LoginToken, User  # noqa: E402

SENTINEL = uuid.uuid4().hex[:10]
DB_URL = os.getenv("DATABASE_URL") or (
    "postgres://{u}:{p}@{h}:{port}/{d}".format(
        u=os.environ["POSTGRES_USER"],
        p=os.environ["POSTGRES_PASSWORD"],
        h=os.environ.get("POSTGRES_HOST", "db"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        d=os.environ["POSTGRES_DB"],
    )
)


def hdr(t: str) -> None:
    print(f"\n=== {t} ===", flush=True)


def second_conn():
    """Independent connection used to observe the DB from outside a transaction."""
    return psycopg.connect(DB_URL, autocommit=True)


def new_user(offset: int) -> User:
    suffix = int(SENTINEL[:4], 16) % 900
    return User.objects.create(
        telegram_id=offset + suffix,
        chat_id=offset + suffix,
        username=f"audit_{SENTINEL}_{offset}",
        first_name="audit",
    )


# --------------------------------------------------------------------------- A
def section_a() -> None:
    hdr("A. effective runtime DB config")
    cfg = connections["default"].settings_dict
    print("ENGINE          :", cfg["ENGINE"])
    print("CONN_MAX_AGE    :", cfg["CONN_MAX_AGE"])
    print("OPTIONS         :", cfg.get("OPTIONS"))
    print("CONN_HEALTH     :", cfg.get("CONN_HEALTH_CHECKS"))
    with connection.cursor() as cur:
        cur.execute("SHOW transaction_isolation")
        print("isolation_level :", cur.fetchone()[0])
    print("autocommit      :", connection.get_autocommit())
    with second_conn() as c, c.cursor() as cur:
        cur.execute("SHOW max_connections")
        print("max_connections :", cur.fetchone()[0])
        cur.execute("SHOW default_transaction_isolation")
        print("server iso lvl  :", cur.fetchone()[0])


# --------------------------------------------------------------------------- B
def section_b() -> None:
    hdr("B. create_draft_ad IntegrityError backstop (no inner savepoint)")
    u = new_user(900_000_900)
    # Pre-create the DRAFT so the second insert hits uq_ads_single_draft_per_user.
    Ad.objects.create(user_id=u.id, status=AdStatus.DRAFT, title="sentinel draft")
    try:
        with transaction.atomic():
            try:
                Ad.objects.create(user_id=u.id, status=AdStatus.DRAFT, title="racer")
            except IntegrityError:
                # exact body of create_draft_ad's recovery branch
                Ad.objects.filter(user_id=u.id, status=AdStatus.DRAFT).delete()
                Ad.objects.create(user_id=u.id, status=AdStatus.DRAFT, title="recovered")
    except Exception as exc:  # noqa: BLE001
        print("recovery branch outcome ->", f"{type(exc).__name__}: {str(exc)[:200]}")
    print("drafts left for user    ->", Ad.objects.filter(user_id=u.id).count())


# --------------------------------------------------------------------------- C
def section_c() -> None:
    hdr("C. record_event inside an open transaction (real FK violation)")
    new_user(800_000_800)
    result: object = "not-called"
    after = "n/a"
    try:
        with transaction.atomic():
            result = record_event(
                AnalyticsEventType.AD_PUBLISHED,
                user_id=10_000_000,  # violates analytics_events_user_id FK
            )
            after = f"next-query-ok count={AnalyticsEvent.objects.count()}"
    except Exception as exc:  # noqa: BLE001
        after = f"{type(exc).__name__}: {str(exc)[:200]}"
    print("record_event returned  ->", result)
    print("caller state afterwards->", after)
    print("needs_rollback flag    ->", connection.needs_rollback)

    hdr("C2. record_event: immediate statement error inside open transaction")
    from django.db import DatabaseError

    real_create = AnalyticsEvent.objects.create

    def _boom(*a, **kw):  # noqa: ANN002, ANN003
        with connection.cursor() as cur:
            cur.execute(
                "INSERT INTO analytics_events (event_type, timestamp) VALUES (%s, %s)",
                ["x" * 200, timezone.now()],  # varchar(30) -> immediate DataError
            )
        return real_create(*a, **kw)

    AnalyticsEvent.objects.create = _boom  # type: ignore[method-assign]
    res2: object = "not-called"
    after2 = "n/a"
    try:
        with transaction.atomic():
            res2 = record_event(AnalyticsEventType.AD_VIEWED)
            after2 = f"next-query-ok count={AnalyticsEvent.objects.count()}"
    except DatabaseError as exc:
        after2 = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        AnalyticsEvent.objects.create = real_create  # type: ignore[method-assign]
    print("record_event returned  ->", res2)
    print("caller state afterwards->", after2)


# --------------------------------------------------------------------------- D/E/F
def section_d() -> None:
    hdr("D. advisory lock: two concurrent sweep attempts")
    order: list[str] = []
    start = threading.Barrier(2)

    def worker(tag: str) -> None:
        start.wait()
        t0 = time.monotonic()
        with transaction.atomic():
            with advisory_lock(AdvisoryLockId.ARCHIVE_SWEEP):
                order.append(f"{tag}-acquired@{t0:.2f}")
                time.sleep(2.0)
                order.append(f"{tag}-released@{time.monotonic():.2f}")
        order.append(f"{tag}-waited={time.monotonic() - t0:.2f}s")
        connections["default"].close()

    ths = [threading.Thread(target=worker, args=(t,)) for t in ("A", "B")]
    for x in ths:
        x.start()
    for x in ths:
        x.join()
    for line in order:
        print("  ", line)

    hdr("E. advisory lock visible in pg_locks while held")
    ev, done = threading.Event(), threading.Event()

    def holder() -> None:
        with transaction.atomic():
            with advisory_lock(AdvisoryLockId.ARCHIVE_SWEEP):
                ev.set()
                done.wait(3.0)
        connections["default"].close()

    th = threading.Thread(target=holder)
    th.start()
    ev.wait(3.0)
    with second_conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND objid=%s",
            (AdvisoryLockId.ARCHIVE_SWEEP,),
        )
        print("   advisory_rows_while_held  =", cur.fetchone()[0])
    done.set()
    th.join()
    time.sleep(0.4)
    with second_conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND objid=%s",
            (AdvisoryLockId.ARCHIVE_SWEEP,),
        )
        print("   advisory_rows_after_commit =", cur.fetchone()[0])

    hdr("F. advisory lock released on ROLLBACK (process-crash proxy)")
    try:
        with transaction.atomic():
            with advisory_lock(AdvisoryLockId.DELETE_SWEEP):
                raise RuntimeError("simulated crash inside sweep")
    except RuntimeError:
        pass
    with second_conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND objid=%s",
            (AdvisoryLockId.DELETE_SWEEP,),
        )
        print("   advisory rows after rollback =", cur.fetchone()[0])


# --------------------------------------------------------------------------- G
def section_g() -> None:
    hdr("G. concurrent LoginToken claim (two 'processes')")
    import hashlib

    raw = (uuid.uuid4().hex + uuid.uuid4().hex)[:32]
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    token = LoginToken.objects.create(
        token_hash=token_hash,
        expires_at=timezone.now() + datetime.timedelta(minutes=5),
    )
    results: list[str] = []
    barrier, lock = threading.Barrier(4), threading.Lock()

    def claim(tid: int) -> None:
        barrier.wait()
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE login_tokens SET telegram_id=%s "
                "WHERE token_hash=%s AND telegram_id IS NULL "
                "AND consumed_at IS NULL AND expires_at > %s RETURNING id",
                [tid, token_hash, timezone.now()],
            )
            row = cur.fetchone()
        with lock:
            results.append(f"tid={tid}->{'CLAIMED' if row else 'none'}")
        connections["default"].close()

    ths = [threading.Thread(target=claim, args=(770_000 + i,)) for i in range(4)]
    for x in ths:
        x.start()
    for x in ths:
        x.join()
    for r in sorted(results):
        print("  ", r)
    print("   claims =", sum(1 for r in results if "CLAIMED" in r))
    token.delete()


# --------------------------------------------------------------------------- H
def section_h() -> None:
    import asyncio

    from telegram_bot.services.ad_data.orm import create_draft_ad

    hdr("H. concurrent create_draft_ad for one user (bot double /post)")
    u = new_user(700_000_700)
    out: list[str] = []

    async def main() -> None:
        res = await asyncio.gather(
            create_draft_ad(u.id), create_draft_ad(u.id), return_exceptions=True
        )
        for i, r in enumerate(res):
            if isinstance(r, BaseException):
                out.append(
                    f"task{i} EXC {type(r).__name__}: {str(r)[:140]}"
                )
            else:
                out.append(f"task{i} ok ad_id={r.id}")

    asyncio.run(main())
    for line in out:
        print("  ", line)
    print("   drafts for user ->", Ad.objects.filter(user_id=u.id).count())

    hdr("H2. create_draft_ad body raced from 6 real threads")
    u2 = new_user(700_001_700)
    res2: list[str] = []
    lk, bar = threading.Lock(), threading.Barrier(6)

    def _body(user_id: int) -> None:
        # Verbatim body of create_draft_ad._create
        try:
            with transaction.atomic():
                existing = Ad.objects.filter(user_id=user_id, status=AdStatus.DRAFT)
                if existing.exists():
                    existing.delete()
                try:
                    r = Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)
                    with lk:
                        res2.append(f"ok ad_id={r.id}")
                except IntegrityError:
                    Ad.objects.filter(user_id=user_id, status=AdStatus.DRAFT).delete()
                    r = Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)
                    with lk:
                        res2.append(f"recovered ad_id={r.id}")
        except Exception as exc:  # noqa: BLE001
            with lk:
                res2.append(f"RAISED {type(exc).__name__}: {str(exc)[:110]}")
        finally:
            connections["default"].close()

    ths = [threading.Thread(target=_body, args=(u2.id,)) for _ in range(6)]
    for x in ths:
        x.start()
    for x in ths:
        x.join()
    for line in sorted(res2):
        print("  ", line)
    print("   drafts for user ->", Ad.objects.filter(user_id=u2.id).count())


# --------------------------------------------------------------------------- I
def section_i() -> None:
    hdr("I. connection behaviour under concurrent load")
    errors: list[str] = []
    barrier, lock = threading.Barrier(16), threading.Lock()

    def worker() -> None:
        try:
            barrier.wait()
            for _ in range(5):
                Ad.objects.count()
                connections["default"].close()
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(f"{type(exc).__name__}: {str(exc)[:110]}")

    ths = [threading.Thread(target=worker) for _ in range(16)]
    for x in ths:
        x.start()
    for x in ths:
        x.join()
    print("   threads=16 queries=5 each -> errors:", len(errors))
    for e in errors[:5]:
        print("     ", e)
    with second_conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname=current_database() AND state='idle in transaction'"
        )
        print("   idle-in-transaction conns ->", cur.fetchone()[0])
        cur.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()"
        )
        print("   total conns to db        ->", cur.fetchone()[0])


# --------------------------------------------------------------------------- J
def section_j() -> None:
    from django.core.management import call_command

    hdr("J. sweep_drafts vs an in-flight bot dialog")
    u = new_user(600_000_600)
    ad = Ad.objects.create(user_id=u.id, status=AdStatus.DRAFT, title="mid-dialog")
    # Simulate a seller who opened /post 31 minutes ago and is still typing.
    Ad.objects.filter(pk=ad.pk).update(
        created_at=timezone.now() - datetime.timedelta(minutes=31)
    )
    row = Ad.objects.get(pk=ad.pk)
    print("   draft created_at ->", row.created_at.isoformat())
    print("   ad.updated_at    ->", row.updated_at.isoformat())
    call_command("sweep_drafts")
    alive = Ad.objects.filter(pk=ad.pk).exists()
    print("   row still present after sweep_drafts ->", alive)
    if not alive:
        try:
            with transaction.atomic():
                Ad.objects.select_for_update().get(pk=ad.pk)
            print("   submit_ad re-fetch -> OK")
        except Ad.DoesNotExist:
            print("   submit_ad re-fetch -> Ad.DoesNotExist (seller loses the ad)")


# --------------------------------------------------------------------------- K
def section_k() -> None:
    hdr("K. delete_sweep (no row lock) vs concurrent reactivation")
    u = new_user(500_000_500)
    ad = Ad.objects.create(
        user_id=u.id,
        status=AdStatus.ARCHIVED,
        title="aged archived ad",
        archived_at=timezone.now() - datetime.timedelta(days=90),
    )
    Ad.objects.filter(pk=ad.pk).update(
        archived_at=timezone.now() - datetime.timedelta(days=90)
    )
    obs: list[str] = []
    bar = threading.Barrier(2)

    def _sweep_select() -> None:
        with transaction.atomic():
            ids = list(
                Ad.objects.filter(
                    status=AdStatus.ARCHIVED,
                    archived_at__lt=timezone.now() - datetime.timedelta(days=60),
                ).values_list("id", flat=True)
            )
            obs.append(f"sweep selected ids={ids}")
            bar.wait()
            n, _ = Ad.objects.filter(id__in=ids).delete()
            obs.append(f"sweep deleted n={n}")
        connections["default"].close()

    def _reactivate() -> None:
        bar.wait()
        with transaction.atomic():
            Ad.objects.select_for_update().get(pk=ad.pk)
            Ad.objects.filter(pk=ad.pk).update(status=AdStatus.ON_MODERATION)
            obs.append("reactivation committed status=ON_MODERATION")
        connections["default"].close()

    ths = [threading.Thread(target=_sweep_select), threading.Thread(target=_reactivate)]
    for x in ths:
        x.start()
    for x in ths:
        x.join()
    for line in obs:
        print("  ", line)
    still = Ad.objects.filter(pk=ad.pk).first()
    print("   final row ->", "GONE" if still is None else still.status)


# --------------------------------------------------------------------------- L
def section_l() -> None:
    import asyncio

    hdr("L. row lock held by sweep -> bot submit_ad + whole bot stall")
    from asgiref.sync import sync_to_async

    u = new_user(400_000_400)
    ad = Ad.objects.create(
        user_id=u.id,
        status=AdStatus.PUBLISHED,
        title="hot ad",
        published_at=timezone.now(),
    )
    lock_held, release = threading.Event(), threading.Event()

    def sweep_like() -> None:
        with transaction.atomic():
            list(Ad.objects.filter(pk=ad.pk).select_for_update().order_by("pk"))
            lock_held.set()
            release.wait(15.0)
        connections["default"].close()

    th = threading.Thread(target=sweep_like)
    th.start()
    lock_held.wait(3.0)

    @sync_to_async
    def bot_submit_shape() -> str:
        t0 = time.monotonic()
        with transaction.atomic():
            Ad.objects.select_for_update().get(pk=ad.pk)
        return f"submit_ad-shaped lock acquired after {time.monotonic() - t0:.2f}s"

    @sync_to_async
    def bot_unrelated_read() -> str:
        t0 = time.monotonic()
        Ad.objects.filter(user_id=u.id).count()
        return f"unrelated bot ORM read took {time.monotonic() - t0:.2f}s"

    async def main() -> None:
        task = asyncio.ensure_future(bot_submit_shape())
        await asyncio.sleep(0.4)
        t0 = time.monotonic()
        res = await bot_unrelated_read()
        print("  ", res, f"(blocked {time.monotonic() - t0:.2f}s wall)")
        release.set()
        print("  ", await task)

    asyncio.run(main())
    th.join()


# --------------------------------------------------------------------------- M
def section_m() -> None:
    from django.conf import settings
    from django.core.management import call_command

    hdr("M. sweep_orphaned_media vs an in-flight submit_ad file move")
    u = new_user(300_000_300)
    ad = Ad.objects.create(user_id=u.id, status=AdStatus.DRAFT, title="media race draft")
    key = f"{SENTINEL}-a1b2c3d4.jpg"
    path = os.path.join(str(settings.MEDIA_ROOT), key)
    # submit_ad: move_staging_to_permanent() has just landed the permanent file;
    # the AdImage INSERT inside transaction.atomic() has NOT committed yet.
    with open(path, "wb") as fh:
        fh.write(b"\xff\xd8\xff\xe0stub")
    print("   planted permanent file ->", path, os.path.exists(path))
    call_command("sweep_orphaned_media")
    print("   file after sweep        ->", os.path.exists(path))
    img = AdImage.objects.create(ad=ad, image=key)
    print("   AdImage row committed   -> id=%s key=%s" % (img.id, img.image))
    print("   file on disk for row    ->", os.path.exists(path))
    print("   => live ad row points at a deleted file:", not os.path.exists(path))
    img.delete()
    ad.delete()
    if os.path.exists(path):
        os.remove(path)


# --------------------------------------------------------------------------- N
def section_n() -> None:
    from django.conf import settings

    from apps.categories.models import Category
    from apps.search.models import SavedSearch, SavedSearchNotification
    from apps.search.services.alert_query import (
        find_matching_ads,
        find_matching_saved_searches,
        record_notifications,
    )

    hdr("N. immediate-alert writer vs daily send_alerts writer")
    u = new_user(200_000_200)
    cat = Category.objects.filter(slug="transport").first() or Category.objects.first()
    ad = Ad.objects.create(
        user_id=u.id,
        status=AdStatus.PUBLISHED,
        title="race listing",
        description="race listing",
        published_at=timezone.now(),
        category=cat,
    )
    ss = SavedSearch.objects.create(
        user=u, query="", is_active=True, category=cat, language="ru"
    )
    print("   IMMEDIATE_ALERTS_ENABLED =", settings.IMMEDIATE_ALERTS_ENABLED)
    a_matches = find_matching_saved_searches(ad)
    print("   A: find_matching_saved_searches ->", [s.pk for s in a_matches])
    b_matches = find_matching_ads(ss)
    print("   B: find_matching_ads (no lock, no notif yet) ->", [a.pk for a in b_matches])
    if a_matches:
        record_notifications(ss, [ad])
    print(
        "   notification rows for (ss, ad) ->",
        SavedSearchNotification.objects.filter(saved_search=ss, ad=ad).count(),
    )
    print(
        "   => A sends and B sends the SAME (saved_search, ad) pair:",
        bool(a_matches) and bool(b_matches),
    )
    ss.delete()
    ad.delete()


# --------------------------------------------------------------------------- O
def section_o() -> None:
    from apps.ads.services.copy_service import copy_ad

    hdr("O. copy_ad (web /copy) while the bot FSM holds a DRAFT")
    u = new_user(100_000_100)
    src = Ad.objects.create(
        user_id=u.id,
        status=AdStatus.PUBLISHED,
        title="source listing",
        published_at=timezone.now(),
    )
    Ad.objects.create(user_id=u.id, status=AdStatus.DRAFT, title="bot fsm draft")
    print("   before copy_ad: drafts =", Ad.objects.filter(user_id=u.id, status=AdStatus.DRAFT).count())
    try:
        copy = copy_ad(src.pk, u.id)
        print("   copy_ad -> ok id=", copy.id)
    except Exception as exc:  # noqa: BLE001
        print("   copy_ad ->", f"{type(exc).__name__}: {str(exc)[:170]}")
    print("   rows after copy_ad ->", list(Ad.objects.filter(user_id=u.id).values_list("id", "title", "status")))
    print("   source ad intact ->", Ad.objects.filter(pk=src.pk).exists())


# --------------------------------------------------------------------------- cleanup
def cleanup() -> None:
    hdr("cleanup sentinel rows")
    Ad.objects.filter(user__username__startswith="audit_").delete()
    User.objects.filter(username__startswith="audit_").delete()
    AnalyticsEvent.objects.filter(event_type=AnalyticsEventType.AD_VIEWED, ad_id__isnull=True, user_id__isnull=True).delete()
    LoginToken.objects.filter(token_hash__startswith="0").filter(
        consumed_at__isnull=True, telegram_id__isnull=True
    ).delete()
    print("   ads left   ->", Ad.objects.filter(user__username__startswith="audit_").count())
    print("   users left ->", User.objects.filter(username__startswith="audit_").count())
    with second_conn() as c, c.cursor() as cur:
        cur.execute("SELECT count(*) FROM pg_locks WHERE locktype='advisory'")
        print("   advisory locks left ->", cur.fetchone()[0])


if __name__ == "__main__":
    for fn in (
        section_a,
        section_b,
        section_c,
        section_d,
        section_g,
        section_h,
        section_i,
        section_j,
        section_k,
        section_l,
        section_m,
        section_n,
        section_o,
    ):
        try:
            fn()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        try:
            connection.close()
        except Exception:  # noqa: BLE001
            pass
    try:
        cleanup()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    sys.stdout.flush()
