"""
Static files storage for the theme app.

Extends whitenoise's CompressedManifestStaticFilesStorage to exclude
Tailwind's ``input.css`` from collectstatic post-processing. The v4-native
``@import "tailwindcss"`` directive in input.css is a standard CSS
``@import`` rule; Django's manifest post-processor resolves it relative to
the file as ``theme/css/tailwindcss``, which does not exist on disk,
causing a MissingFileError. input.css is a build-time-only input for the
Tailwind CLI and is never referenced by templates — only output.css is served.

Implementation note: Django's ``ignore_patterns`` is NOT a storage-class
mechanism — it lives on ``StaticFilesConfig`` (AppConfig) and is consumed
by the ``collectstatic`` command during file discovery (via finders),
not during ``post_process``. Setting it on the storage class is a no-op.
The correct approach is to override ``post_process`` and filter the file
out before the parent class applies CSS ``@import``/``url()`` rewriting.
"""

import fnmatch

from whitenoise.storage import CompressedManifestStaticFilesStorage


class ThemeStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Static files storage that excludes Tailwind input.css from post-processing.

    ``input.css`` contains ``@import "tailwindcss"`` (v4 syntax) which
    collectstatic's manifest post-processor would try to resolve as a relative
    CSS file reference, causing a MissingFileError. The file is a build-time-only
    input for the Tailwind CLI and is never referenced by templates.
    """

    # Retained for StaticFilesConfig-level discover-time filtering if needed.
    # Does NOT affect post_process — overridden below instead.
    ignore_patterns = ["theme/css/input.css"]

    def post_process(self, paths, content_hashed=False, **kwargs):
        """Filter out input.css before the parent runs CSS @import/url() rewriting.

        Django's HashedFilesMixin builds an ``adjustable_paths`` list from
        ``self._patterns`` (CSS/JS regexes) and processes every file in
        ``paths``. Since input.css matches the ``*.css`` pattern, it would have
        its ``@import`` rules resolved, causing MissingFileError. This override
        removes it from the dict before delegating to the parent.
        """
        skip_patterns = ["theme/css/input.css"]
        filtered = {
            name: value
            for name, value in paths.items()
            if not any(fnmatch.fnmatch(name, pattern) for pattern in skip_patterns)
        }
        yield from super().post_process(
            filtered, content_hashed=content_hashed, **kwargs
        )
