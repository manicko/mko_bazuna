"""Generate tree-format text output from categories.yaml."""
import yaml
from pathlib import Path

YAML_PATH = Path(__file__).parent / "categories_tree.txt"
SRC = Path(__file__).parent / "categories.yaml"


def format_node(node, indent_level):
    level = node["level"]
    name = node["name"]
    slug = node["slug"]
    mc_id = node["avito_mc_id"]
    subs = len(node.get("subcategories", []))
    prefix = "  " * indent_level
    return f"{prefix}L{level} [{mc_id}] {name} (slug: {slug}, {subs} subs)\n"


def render_tree(node, indent_level, lines):
    lines.append(format_node(node, indent_level))
    for child in node.get("subcategories", []):
        render_tree(child, indent_level + 1, lines)


def main():
    with open(SRC, encoding="utf-8") as f:
        root = yaml.safe_load(f)
    lines = []
    render_tree(root, 0, lines)
    output = "".join(lines)
    YAML_PATH.write_text(output, encoding="utf-8")
    print(f"Written {len(output)} chars to {YAML_PATH}")
    # Quick sanity: count lines and verify structure
    total_lines = len(output.strip().splitlines())
    print(f"Total lines: {total_lines}")


if __name__ == "__main__":
    main()
