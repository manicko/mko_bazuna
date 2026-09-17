"""Shared i18n test helpers.

Provides the canonical ``_parse_po_entries`` parser used by the i18n
completeness and pipeline test suites so both share a single source of
truth for ``.po`` entry parsing (plural-aware, stdlib-only — no ``polib``).
"""

from __future__ import annotations


def _parse_po_entries(text: str) -> list[tuple[str, str]]:
    """Parse ``.po`` text into ``(msgid, msgstr)`` tuples.

    Handles both simple and plural entries. For plural entries
    (``msgid_plural`` / ``msgstr[N]``), the singular ``msgid`` and the
    ``msgid_plural`` are both returned as separate tuples sharing the
    first ``msgstr`` value encountered.
    """
    entries: list[tuple[str, str]] = []
    cur_msgid: list[str] = []
    cur_msgstr: list[str] = []
    cur_plural: list[str] = []
    in_msgstr = False

    def _unescape(s: str) -> str:
        s = s.strip()
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        return s.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")

    def _flush() -> None:
        if in_msgstr:
            entries.append(("".join(cur_msgid), "".join(cur_msgstr)))
        if cur_plural:
            entries.append(("".join(cur_plural), "".join(cur_msgstr)))

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("msgid "):
            _flush()
            cur_msgid = [_unescape(stripped[len("msgid ") :])]
            cur_msgstr = []
            cur_plural = []
            in_msgstr = False
        elif stripped.startswith("msgid_plural "):
            cur_plural = [_unescape(stripped[len("msgid_plural ") :])]
        elif stripped.startswith("msgstr"):
            in_msgstr = True
            rest = stripped[len("msgstr") :]
            if rest.startswith("["):
                rest = rest[rest.index("]") + 1 :]
            cur_msgstr = [_unescape(rest)]
        elif stripped.startswith('"') and in_msgstr:
            cur_msgstr.append(_unescape(stripped))
        elif stripped.startswith('"') and cur_plural:
            cur_plural.append(_unescape(stripped))
        elif stripped.startswith('"') and cur_msgid:
            cur_msgid.append(_unescape(stripped))
        elif stripped == "" and (in_msgstr or cur_plural):
            _flush()
            cur_msgid = []
            cur_msgstr = []
            cur_plural = []
            in_msgstr = False

    _flush()

    return entries
