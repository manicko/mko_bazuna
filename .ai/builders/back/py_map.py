"""Semantic map builder for the Python source tree.

Walks ``SRC_ROOT``, parses every ``.py`` file with the ``ast`` module, and
emits two JSON files:

    .ai/structure/back/py_map.json      -> one entry per source file
    .ai/structure/back/py_anchors.json  -> semantic anchors (calls, returns)

Design notes:
* Uses only the Python standard library (``ast``, ``json``, ``logging`` ...).
* Honors ``.gitignore`` via ``git check-ignore`` so generated/ignored paths
  are excluded. Falls back to a hardcoded ignore set when git is unavailable.
* Layer detection follows the precedence defined in ``config.LAYER_PATTERNS``.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (  # noqa: E402
    DEFAULT_LAYER,
    IGNORE_DIRS,
    IGNORE_EXTENSIONS,
    LAYER_PATTERNS,
    OUTPUT_BACK,
    SRC_ROOT,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Git ignore handling
# ============================================================================


def _is_git_available(root: Path) -> bool:
    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(root),
            check=True,
            capture_output=True,
        )
    except OSError, subprocess.CalledProcessError:
        return False
    return True


class GitIgnoreFilter:
    """Exclude paths matched by ``.gitignore`` using ``git check-ignore``.

    Results for individual paths are cached because a single ``git`` invocation
    can evaluate many paths at once; we batch lazily on first use.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._enabled = _is_git_available(root)
        self._ignored: set[str] = set()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def is_ignored(self, file_path: Path) -> bool:
        if not self._enabled:
            return False
        try:
            rel = file_path.relative_to(self._root).as_posix()
        except ValueError:
            return False
        result = subprocess.run(
            ["git", "check-ignore", "--", rel],
            cwd=str(self._root),
            capture_output=True,
            text=True,
        )
        return result.returncode == 0


# ============================================================================
# Layer detection
# ============================================================================


def detect_layer(file_path: str) -> str:
    """Return the semantic layer for a POSIX-style file path."""
    posix = file_path.replace("\\", "/")
    for layer, marker in LAYER_PATTERNS:
        if marker in posix:
            return layer
    return DEFAULT_LAYER


# ============================================================================
# AST collector
# ============================================================================


class SemanticCollector(ast.NodeVisitor):
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.class_stack: list[str] = []
        self.function_stack: list[str] = []
        self.imports: list[str] = []
        self.classes: list[str] = []
        self.functions: list[str] = []
        self.anchors: list[dict] = []

    # -------------------------------------------------------------- class

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.classes.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    # ----------------------------------------------------------- function

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append(node.name)
        self.functions.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.function_stack.append(node.name)
        self.functions.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    # ------------------------------------------------------------- import

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.imports.append(node.module)
        self.generic_visit(node)

    # --------------------------------------------------------------- call

    def visit_Call(self, node: ast.Call) -> None:
        func_name = self._call_name(node.func)
        if func_name:
            self.anchors.append(self._make_anchor("function_call", func_name))
        self.generic_visit(node)

    # ------------------------------------------------------------- return

    def visit_Return(self, node: ast.Return) -> None:
        self.anchors.append(self._make_anchor("return_statement", "return"))
        self.generic_visit(node)

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _call_name(func: ast.AST) -> str | None:
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return None

    def _symbol_path(self) -> list[str]:
        return self.class_stack + self.function_stack

    def _make_anchor(self, anchor_type: str, value: str) -> dict:
        stable = self._build_hash(anchor_type, value)
        return {
            "id": stable,
            "symbol_path": self._symbol_path(),
            "type": anchor_type,
            "value": value,
            "stable_hash": stable,
        }

    def _build_hash(self, anchor_type: str, value: str) -> str:
        raw = f"{self.file_path}|{self._symbol_path()}|{anchor_type}|{value}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]


# ============================================================================
# Main
# ============================================================================


def _module_name(file_path: Path, root: Path) -> str:
    rel = file_path.relative_to(root).with_suffix("")
    return rel.as_posix().replace("/", ".")


def build() -> dict:
    if not SRC_ROOT.exists():
        logger.warning("SRC_ROOT does not exist: %s", SRC_ROOT)
        return {"files": [], "anchors": []}

    git_filter = GitIgnoreFilter(SRC_ROOT)

    semantic_graph: dict[str, list] = {"files": [], "anchors": []}

    for file in sorted(SRC_ROOT.rglob("*.py")):
        if file.suffix in IGNORE_EXTENSIONS:
            continue
        if any(part in IGNORE_DIRS for part in file.parts):
            continue
        if git_filter.is_ignored(file):
            continue

        try:
            # utf-8-sig transparently strips a leading BOM when present.
            code = file.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            logger.warning("Skipping non-utf8 file: %s", file)
            continue

        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            logger.warning("Parse error in %s: %s", file, exc)
            continue

        collector = SemanticCollector(str(file))
        collector.visit(tree)

        posix_path = file.relative_to(SRC_ROOT).as_posix()
        semantic_graph["files"].append(
            {
                "path": posix_path,
                "module": _module_name(file, SRC_ROOT),
                "layer": detect_layer(posix_path),
                "imports": collector.imports,
                "classes": collector.classes,
                "functions": collector.functions,
            }
        )

        for anchor in collector.anchors:
            anchor["file"] = posix_path
            semantic_graph["anchors"].append(anchor)

    return semantic_graph


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    OUTPUT_BACK.mkdir(parents=True, exist_ok=True)
    graph = build()

    map_path = OUTPUT_BACK / "py_map.json"
    anchors_path = OUTPUT_BACK / "py_anchors.json"

    map_path.write_text(
        json.dumps(graph["files"], indent=2, ensure_ascii=False), encoding="utf-8"
    )
    anchors_path.write_text(
        json.dumps(graph["anchors"], indent=2, ensure_ascii=False), encoding="utf-8"
    )

    logger.info("Generated %s (%d files)", map_path, len(graph["files"]))
    logger.info("Generated %s (%d anchors)", anchors_path, len(graph["anchors"]))


if __name__ == "__main__":
    main()
