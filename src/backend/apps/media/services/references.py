"""
AdImage storage-key liveness: which keys no row references any more.

This module owns the **sole** "is this storage key still referenced by an
``AdImage`` row?" predicate.  ``apps.media.signals`` consumes it to decide
which files may be freed, and any future caller (e.g. a moderator single-photo
removal) must compose this function rather than re-implement the predicate.

Why the predicate is evaluated **after commit, in the caller's
``transaction.on_commit`` closure**: Django's ``Collector.delete()`` sends
``pre_delete`` for *every* collected instance **before** it runs any
``DELETE``.  A reference check taken at ``pre_delete`` time therefore still
sees sibling rows that are about to disappear, so two rows sharing a key in a
single cascade each observe the other as present and both decline to free the
file -- after commit, zero rows reference it and the file leaks.  Evaluating
after commit, when the departing rows are already gone, removes that cause and
also narrows the concurrent-insert race from the whole transaction down to the
gap between one reference query and one ``unlink``.

Why the predicate is **unexcluded** ("referenced by any row"): by closure time
the rows scheduled for deletion have already been removed, so there is no
self-reference left to exclude.  An ``.exclude(pk=instance.pk)`` would in fact
be unsafe here -- ``Collector`` sets ``instance.pk = None`` after its
``atomic()`` block, and ``.exclude(pk=None)`` raises ``ValueError``.

The four key columns are **duplicated** from ``AdImage`` rather than derived:
the model carries no marker distinguishing key columns from the non-key
``telegram_file_id`` / ``sha256`` fields, so derivation would require a model
change.  The drift risk is instead pinned by a relational test asserting that
:data:`KEY_COLUMNS` names resolve to concrete model fields **and** that a
fully-populated ``AdImage``'s ``storage_keys()`` equals ``list(KEY_COLUMNS)``.

This module is a **database predicate only** -- it performs no filesystem
I/O.  The signal retains ownership of key collection, ``on_commit``
registration and the filesystem error boundary.
"""

from collections.abc import Sequence
from typing import Final

from django.db.models import Q

from apps.ads.models import AdImage

KEY_COLUMNS: Final[tuple[str, ...]] = (
    "image",
    "thumbnail_small",
    "thumbnail_medium",
    "thumbnail_large",
)


def unreferenced_keys(keys: Sequence[str]) -> list[str]:
    """Return the subset of *keys* referenced by no ``AdImage`` row.

    Blank/falsy keys are dropped from the candidate set (they never denote a
    real file).  When no candidate remains, ``[]`` is returned without issuing
    a query.

    The check is one combined four-column ``Q`` in a **single** statement --
    ``Q(image__in=...) | Q(thumbnail_small__in=...) | Q(thumbnail_medium__in=...)
    | Q(thumbnail_large__in=...)`` -- so PostgreSQL makes one snapshot and one
    planning pass and builds a ``BitmapOr`` over the four existing btree
    indexes.  Chaining one query per column was measured ~3x slower.  The
    statement terminates in a per-key projection rather than ``.exists()``:
    this function must answer *which* of the input keys are unreferenced, and
    ``.exists()`` collapses that to a single boolean.

    The result preserves the **input order** of *keys* -- callers such as
    ``apps.users`` deletion assert ordered list equality.

    Args:
        keys: Candidate storage keys to test for liveness.

    Returns:
        The unreferenced keys, in the same relative order as *keys*.
    """
    candidates = [key for key in keys if key]
    if not candidates:
        return []

    key_q = (
        Q(image__in=candidates)
        | Q(thumbnail_small__in=candidates)
        | Q(thumbnail_medium__in=candidates)
        | Q(thumbnail_large__in=candidates)
    )
    referenced: set[str] = set()
    for values in AdImage.objects.filter(key_q).values_list(*KEY_COLUMNS):
        referenced.update(value for value in values if value)

    return [key for key in candidates if key not in referenced]
