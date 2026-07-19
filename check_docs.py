#!/usr/bin/env python3
"""
Check documentation for cross-link validity and redundancy.
"""
import os
import sys
from pathlib import Path

def check_cross_links():
    """Verify all cross-links point to existing files."""
    print("=== Cross-link Validation ===")
    
    # All main documentation files to check
    docs_dir = Path("docs")
    
    # Files with internal references to check
    all_files = list(docs_dir.rglob("*.md")) + [
        Path("README.md"),
        Path("AGENTS.md")
    ]
    
    errors = []
    for file_path in all_files:
        if not file_path.exists():
            continue
            
        try:
            content = file_path.read_text()
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            continue
        
        # Find all relative markdown links (e.g., [text](../01-auth/auth-api.md) or [text](file.md))
        import re
        
        # Pattern matches [text](relative/path.md)
        pattern = r'\[([^\]]+)\]\(([^)]+\.md)\)'
        matches = re.findall(pattern, content)
        
        for link_text, link_target in matches:
            # Convert relative path to absolute
            target_path = (file_path.parent / link_target).resolve()
            
            if not target_path.exists():
                errors.append(f"{file_path}: broken link -> {link_target} (not found)")
    
    if errors:
        print(f"Found {len(errors)} broken links:")
        for error in errors:
            print(f"  ✗ {error}")
        return False
    else:
        print("✓ All cross-links are valid")
        return True

def check_redundancy():
    """Check for content redundancy between SPEC.md and wiki files."""
    print("\n=== Redundancy Check ===")
    
    spec_path = Path("docs/SPEC.md")
    wiki_files = [
        Path("docs/wiki/technical-specification.md"),
        Path("docs/wiki/db-structure.md"),
        Path("docs/wiki/architecture-structure.md"),
        Path("docs/wiki/packages.md"),
        Path("docs/wiki/audit-resolutions.md")
    ]
    
    # Read SPEC content
    spec_content = spec_path.read_text()
    
    # Check for unique sections in SPEC
    spec_sections = [line for line in spec_content.split('\n') if line.startswith('## ')]
    print(f"SPEC.md sections: {len(spec_sections)}")
    print(spec_sections)
    
    # Check if any wiki content is duplicated in SPEC (basic check)
    wiki_content = []
    for wiki_file in wiki_files:
        wiki_content.append(wiki_file.read_text())
    
    redundancy_found = False
    for i, wiki_content in enumerate(wiki_content):
        wiki_file = wiki_files[i]
        # Count overlapping words (simple check)
        spec_words = set(spec_content.lower().split())
        wiki_words = set(wiki_content.lower().split())
        overlap = spec_words.intersection(wiki_words)
        
        overlap_ratio = len(overlap) / len(spec_words) if spec_words else 0
        
        if overlap_ratio > 0.3:
            print(f"⚠️  Potential redundancy: {wiki_file.name} shares {len(overlap)} words with SPEC.md ({overlap_ratio:.1%})")
            redundancy_found = True
    
    if not redundancy_found:
        print("✓ No significant redundancy detected")
    
    return not redundancy_found

def check_file_structure():
    """Validate file structure follows conventions."""
    print("\n=== File Structure Validation ===")
    
    issues = []
    
    # Check that 00-overview/doc-maintenance-rules.md exists
    rules_path = Path("docs/00-overview/doc-maintenance-rules.md")
    if not rules_path.exists():
        issues.append("doc-maintenance-rules.md not found in 00-overview")
    
    # Check that 98-reference/ast-editor.md exists
    ast_editor_path = Path("docs/98-reference/ast-editor.md")
    if not ast_editor_path.exists():
        issues.append("ast-editor.md not found in 98-reference")
    
    # Check frontmatter patterns
    yaml_files = list(Path("docs").rglob("*.md"))
    for yaml_file in yaml_files:
        content = yaml_file.read_text()
        if not content.startswith("---\n"):
            issues.append(f"{yaml_file}: missing YAML frontmatter")
    
    if issues:
        print("Structure issues found:")
        for issue in issues:
            print(f"  ✗ {issue}")
        return False
    else:
        print("✓ File structure is valid")
        return True

def main():
    os.chdir(Path(__file__).parent)
    
    print("Checking Mko Bazuna documentation for final polish...")
    print(f"Working directory: {os.getcwd()}")
    
    all_ok = True
    
    # Run checks
    if not check_cross_links():
        all_ok = False
    
    if not check_redundancy():
        all_ok = False
    
    if not check_file_structure():
        all_ok = False
    
    print("\n=== Summary ===")
    if all_ok:
        print("✓ Documentation is clean, navigable, and rule-compliant")
        print("✓ No broken links, redundancy, or structure issues")
        return 0
    else:
        print("❌ Documentation issues detected")
        return 1

if __name__ == "__main__":
    sys.exit(main())