"""Guardrail test: ensure adapters/module_wrapper/ has no domain imports.

This test scans all Python files in adapters/module_wrapper/ and verifies
that none of them import from domain-specific modules (gchat, gmail, etc.).

The module_wrapper layer must remain domain-agnostic so that adding a new
wrapper only requires configuration, not modifying adapter internals.
"""

import ast
import os
from pathlib import Path

import pytest

# Domain modules that must NOT be imported from adapters/module_wrapper/
DOMAIN_MODULES = {
    "gchat",
    "gmail",
    "middleware.qdrant_core",
    "gchat.card_framework_wrapper",
    "gchat.wrapper_setup",
    "gchat.structure_dsl",
    "gmail.email_wrapper_setup",
}

ADAPTER_DIR = Path(__file__).resolve().parents[2] / "adapters" / "module_wrapper"


def _get_imports(filepath: Path) -> list[tuple[str, int]]:
    """Extract all import statements from a Python file.

    Returns:
        List of (module_name, line_number) tuples
    """
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append((node.module, node.lineno))

    return imports


def _is_domain_import(module_name: str) -> bool:
    """Check if an import references a domain-specific module."""
    for domain in DOMAIN_MODULES:
        if module_name == domain or module_name.startswith(f"{domain}."):
            return True
    return False


def _collect_violations() -> list[str]:
    """Scan all .py files in adapters/module_wrapper/ for domain imports."""
    violations = []

    for py_file in sorted(ADAPTER_DIR.glob("*.py")):
        if py_file.name.startswith("__"):
            continue

        for module_name, lineno in _get_imports(py_file):
            if _is_domain_import(module_name):
                violations.append(
                    f"{py_file.name}:{lineno} imports '{module_name}'"
                )

    return violations


class TestWrapperAgnostic:
    """Ensure adapters/module_wrapper/ has no domain-specific imports."""

    def test_no_domain_imports(self):
        """No file in adapters/module_wrapper/ should import gchat, gmail, etc."""
        violations = _collect_violations()

        if violations:
            msg = (
                f"Found {len(violations)} domain import(s) in "
                f"adapters/module_wrapper/:\n"
                + "\n".join(f"  - {v}" for v in violations)
                + "\n\nThe module_wrapper layer must remain domain-agnostic. "
                "Move domain-specific code to the consumer (e.g. gchat/wrapper_setup.py)."
            )
            pytest.fail(msg)

    def test_adapter_dir_exists(self):
        """Sanity check that the adapter directory exists."""
        assert ADAPTER_DIR.exists(), f"Expected directory: {ADAPTER_DIR}"
        py_files = list(ADAPTER_DIR.glob("*.py"))
        assert len(py_files) > 5, (
            f"Expected >5 .py files in {ADAPTER_DIR}, found {len(py_files)}"
        )
