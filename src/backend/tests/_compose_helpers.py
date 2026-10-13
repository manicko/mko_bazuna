"""Shared helpers for compose-file structural tests.

Extracted from ``test_compose_hardening.py`` and ``test_deploy_workflow.py``
to eliminate the byte-for-byte duplicate ``_service_block`` (B9-02).
"""

from __future__ import annotations

import re
from pathlib import Path


def _service_block(compose_path: Path, service_name: str) -> str:
    """Extract a service's YAML block from a compose file.

    Services are 2-space-indented keys under ``services:``.  The block
    extends until the next 2-space service definition or a 0-indent
    top-level key (e.g. ``volumes:``).
    """
    text = compose_path.read_text()
    pattern = rf"^  {re.escape(service_name)}:\s*$"
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if re.match(pattern, line):
            start = i
            break
    if start is None:
        return ""
    block: list[str] = [lines[start]]
    for line in lines[start + 1 :]:
        # Stop at a 0-indented top-level key (not a comment or empty line).
        if line and not line.startswith(" "):
            break
        # Stop at the next sibling service (exactly 2-space indent).
        if re.match(r"^  [A-Za-z_][A-Za-z0-9_]*:\s*$", line):
            break
        block.append(line)
    return "\n".join(block)
