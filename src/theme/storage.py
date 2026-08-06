"""
Static files storage for the theme app.

Extends whitenoise's CompressedManifestStaticFilesStorage to exclude
Tailwind's ``input.css`` from collectstatic post-processing. The v4-native
``@import "tailwindcss"`` directive in input.css is a standard CSS
``@import`` rule; collectstatic's manifest post-processor would try to
resolve it as a relative file reference (looking for ``theme/css/tailwindcss``)
and fail with MissingFileError. input.css is a build-time-only input for the
Tailwind CLI and is never referenced by templates — only output.css is served.
"""

from whitenoise.storage import CompressedManifestStaticFilesStorage


class ThemeStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """CompressedManifestStaticFilesStorage that skips Tailwind input.css."""

    ignore_patterns = ["theme/css/input.css"]
