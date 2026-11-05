"""
Pydantic DTOs for the media subsystem.

Provides ``SubmittedPhoto`` — the validated shape of a photo dict at the ad
submission boundary.  By coercing raw dicts (produced by the bot FSM and tests)
into this model at ``SubmitAdInput`` construction, malformed photos are rejected
*before* any filesystem or database write occurs (10-QLT-008).

This module is a leaf — it imports only ``pydantic`` (and the ``core`` base
schema) — so that ``media.services.filesystem`` can import it without creating
an import cycle (``submission.py`` imports ``filesystem.py`` at module level,
so the reverse direction is forbidden).  ``SubmittedPhoto`` exposes a pure
``storage_keys()`` field accessor mirroring ``AdImage.storage_keys()``; it
imports nothing and deletes nothing, so the leaf claim still holds — do **not**
"fix" the apparent asymmetry by importing ``STAGING_PREFIX`` or any filesystem
helper here.
"""

from __future__ import annotations

from apps.core.schemas import BaseInputModel

__all__ = ["SubmittedPhoto"]


class SubmittedPhoto(BaseInputModel):
    """A single photo's storage metadata as submitted by the bot FSM.

    The bot's ``process_photos`` handler builds dicts with ``storage_key``,
    ``telegram_file_id``, and ``position``.  Thumbnail keys are attached later
    by ``submit_ad`` during the pre-transaction thumbnail pipeline.

    Validating this shape at the ``SubmitAdInput`` boundary ensures that a
    missing ``storage_key`` (the one required field) raises ``ValidationError``
    before any DB write — the core goal of 10-QLT-008.

    Pydantic v2 coerces plain dicts into this model automatically when the
    parent ``SubmitAdInput`` is constructed, so producers that still emit dicts
    (the bot handler, integration tests) require no changes.
    """

    storage_key: str
    telegram_file_id: str | None = None
    position: int = 0
    thumbnail_small: str | None = None
    thumbnail_medium: str | None = None
    thumbnail_large: str | None = None

    def storage_keys(self) -> list[str]:
        """Return this photo's non-empty storage keys.

        Mirrors ``AdImage.storage_keys()`` — same four fields, same order — so
        a reclaim can be keyed off a submitted photo exactly as a deletion is
        keyed off a persisted row.

        Returns **permanent-form** keys: ``plan_staging_promotion`` and the
        thumbnail pipeline rewrite the staging prefix away in place before any
        caller reads these fields, so callers that need the staged path compose
        ``STAGING_PREFIX + key`` themselves.  Do not ``removeprefix`` here.

        Pure field access — no I/O, no imports, no byte deletion.
        """
        return [
            key
            for key in (
                self.storage_key,
                self.thumbnail_small,
                self.thumbnail_medium,
                self.thumbnail_large,
            )
            if key
        ]
