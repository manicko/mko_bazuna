import hashlib
from pathlib import Path

import ast
import yaml

IGNORE_DIRS = {".venv", "node_modules", "__pycache__", ".git", "dist", "build"}

ROOT = Path(__file__).parent.parent.parent.parent / "src"
OUTPUT = Path(__file__).parent.parent.parent / "structure/back"


class SemanticCollector(ast.NodeVisitor):
    def __init__(self, file_path):
        self.file_path = str(file_path)

        self.class_stack = []
        self.function_stack = []

        self.imports = []
        self.classes = []
        self.functions = []
        self.anchors = []

    # =========================================================
    # CLASS
    # =========================================================

    def visit_ClassDef(self, node):
        class_name = node.name

        self.class_stack.append(class_name)

        self.classes.append(class_name)

        self.generic_visit(node)

        self.class_stack.pop()

    # =========================================================
    # FUNCTION
    # =========================================================

    def visit_FunctionDef(self, node):
        function_name = node.name

        self.function_stack.append(function_name)

        self.functions.append(function_name)

        self.generic_visit(node)

        self.function_stack.pop()

    # =========================================================
    # IMPORTS
    # =========================================================

    def visit_ImportFrom(self, node):
        if node.module:
            self.imports.append(node.module)

        self.generic_visit(node)

    # =========================================================
    # CALLS
    # =========================================================

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            function_name = node.func.id

            self.anchors.append({
                "id": self.build_hash("function_call", function_name),
                "symbol_path": self.get_symbol_path(),
                "type": "function_call",
                "value": function_name,
                "stable_hash": self.build_hash("function_call", function_name),
            })

        self.generic_visit(node)

    # =========================================================
    # RETURNS
    # =========================================================

    def visit_Return(self, node):
        self.anchors.append({
            "id": self.build_hash("return_statement", "return"),
            "symbol_path": self.get_symbol_path(),
            "type": "return_statement",
            "stable_hash": self.build_hash("return_statement", "return"),
        })

        self.generic_visit(node)

    # =========================================================
    # HELPERS
    # =========================================================

    def get_symbol_path(self):
        return self.class_stack + self.function_stack

    def build_hash(self, anchor_type, value):
        raw = f"{self.file_path}|{self.get_symbol_path()}|{anchor_type}|{value}"

        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]


# =============================================================
# MAIN
# =============================================================


semantic_graph = {"files": [], "anchors": []}

for file in ROOT.rglob("*.py"):
    if any(part in IGNORE_DIRS for part in file.parts):
        continue

    try:
        code = file.read_text(encoding="utf-8")

    except UnicodeDecodeError:
        print(f"Skipping non-utf8 file: {file}")

        continue

    try:
        module = ast.parse(code)

    except Exception as e:
        print(f"Parse error in {file}: {e}")

        continue

    collector = SemanticCollector(file)

    collector.visit(module)

    # =========================================================
    # FILE MAP
    # =========================================================

    semantic_graph["files"].append({
        "path": str(file),
        "module": str(file).replace("/", ".").replace("\\", ".").replace(".py", ""),
        "layer": (
            "api"
            if "/api/" in str(file)
            else "service"
            if "/services/" in str(file)
            else "model"
            if "/models/" in str(file)
            else "unknown"
        ),
        "imports": collector.imports,
        "classes": collector.classes,
        "functions": collector.functions,
    })

    # =========================================================
    # ANCHORS
    # =========================================================

    for anchor in collector.anchors:
        anchor["file"] = str(file)

        semantic_graph["anchors"].append(anchor)

# =============================================================
# SAVE
# =============================================================


with open(Path(OUTPUT / "py_map.yaml"), "w") as f:
    yaml.dump(semantic_graph["files"], f, sort_keys=False, allow_unicode=True)

print("Generated " + str(OUTPUT / "py_map.yaml"))


with open(Path(OUTPUT / "py_anchors.yaml"), "w") as f:
    yaml.dump(semantic_graph["anchors"], f, sort_keys=False, allow_unicode=True)

print("Generated " + str(OUTPUT / "py_anchors.yaml"))
