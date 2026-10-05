"""
The ``AdImage`` key-column vocabulary.

This module owns the **vocabulary** of ``AdImage`` key column names.  It owns
no predicate, no query, no filesystem operation, and no model definition -- it
is a single ordered tuple of names and nothing else.

``references`` remains the **sole owner** of the still-referenced predicate,
``media_gate`` owns its authorisation predicate, and ``sweep_orphaned_media``
owns its census.  Those three are **semantically independent by design and must
not be merged**: folding the authorisation filter into a shared helper would
make unpublished/declined ads' images publicly readable, and replacing the
census with a candidate probe would delete every file outside the candidate
list.

The tuple is **deliberately duplicated from** ``AdImage``: the model carries no
marker separating key columns from the non-key ``telegram_file_id`` / ``sha256``
fields, so deriving it would require a model change.  The drift risk is guarded
by named tests rather than by derivation.

Leaf module: it performs no ``apps.*`` imports, no model access, and no
module-level side effects (``django.*`` and stdlib imports would be permitted;
none are needed here).

Adding a key column is a **multi-file change** -- this tuple, the ``AdImage``
field, a migration, an index, the ``KEY_FORMAT_REGEX`` constraint,
``ThumbnailSizeStrEnum``, and ``ThumbnailService.SIZES``.  **The tests are the
tripwire.**
"""

from typing import Final

KEY_COLUMNS: Final[tuple[str, ...]] = (
    "image",
    "thumbnail_small",
    "thumbnail_medium",
    "thumbnail_large",
)
