"""Guard: published code must never import from the internal `research/` tree.

Background — this test exists because of a real outage. Commit 59207e9 removed
`research/` from the published repo, but production kept importing model classes
from `research.trm.h2.*`. Both the learned search scorer and the card builder's
slot assignment caught the resulting ImportError in a broad `except`, logged, and
silently degraded to heuristics. That went unnoticed for roughly three months.

The fix was to move the inference definitions into `adapters/` (unified_trn,
slot_assigner, domain_config, eval_metrics) and leave only training scripts in
`research/`. These tests keep it that way:

  1. No shipped module may reference `research.` at all (static scan).
  2. The model classes and their checkpoints must load from `adapters/` alone.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories that ship in the published repo and therefore must stay clean.
SHIPPED_DIRS = [
    "adapters",
    "gchat",
    "gmail",
    "tools",
    "config",
    "middleware",
    "auth",
    "resources",
]

# `research/` itself and its own shims are exempt, as are these tests.
EXEMPT_PARTS = {".venv", "__pycache__", "node_modules", ".claude", "research"}


def _shipped_python_files() -> list[Path]:
    files: list[Path] = []
    for d in SHIPPED_DIRS:
        root = REPO_ROOT / d
        if not root.is_dir():
            continue
        for p in root.rglob("*.py"):
            if EXEMPT_PARTS & set(p.relative_to(REPO_ROOT).parts):
                continue
            files.append(p)
    return files


def _research_imports(path: Path) -> list[str]:
    """Return `research.*` imports in a file, including function-local ones."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []

    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import and can never reach research/
            if node.level == 0 and (node.module or "").split(".")[0] == "research":
                offenders.append(f"line {node.lineno}: from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "research":
                    offenders.append(f"line {node.lineno}: import {alias.name}")
    return offenders


def test_no_shipped_module_imports_research():
    """Static scan — catches the exact regression that broke the learned stack."""
    files = _shipped_python_files()
    assert files, "found no shipped Python files to scan — check SHIPPED_DIRS"

    violations = {
        str(p.relative_to(REPO_ROOT)): found
        for p in files
        if (found := _research_imports(p))
    }

    assert not violations, (
        "Shipped code imports from the internal research/ tree, which is absent "
        "from the published repo. Move the definition into adapters/ instead.\n"
        + "\n".join(
            f"  {path}\n    " + "\n    ".join(hits)
            for path, hits in sorted(violations.items())
        )
    )


@pytest.mark.parametrize(
    "module_path,symbol",
    [
        ("adapters.unified_trn", "UnifiedTRN"),
        ("adapters.slot_assigner", "SlotAffinityNet"),
        ("adapters.domain_config", "resolve_domain"),
        ("adapters.eval_metrics", "reciprocal_rank"),
    ],
)
def test_inference_definitions_live_in_adapters(module_path, symbol):
    """The symbols production needs must be importable without research/."""
    module = importlib.import_module(module_path)
    assert hasattr(module, symbol), f"{module_path} is missing {symbol}"


def test_learned_scorer_loads_when_checkpoint_present():
    """A resolvable checkpoint must actually produce a model, not a silent None.

    This is the assertion that fails loudly if the model class goes missing
    again: checkpoint resolution succeeding while loading returns None is
    precisely the signature of the outage described above.
    """
    pytest.importorskip("torch")
    from adapters.module_wrapper.search_mixin import SearchMixin

    checkpoint = SearchMixin._resolve_checkpoint_path()
    if not checkpoint:
        pytest.skip("no learned-scorer checkpoint available in this environment")

    SearchMixin._learned_model = None  # bypass class-level cache
    try:
        model = SearchMixin._load_learned_model()
    finally:
        SearchMixin._learned_model = None

    assert model is not None, (
        f"checkpoint resolved to {checkpoint} but the model failed to load — "
        "the learned scorer is silently degrading to multidim"
    )


def test_slot_assignment_loads_when_checkpoint_present():
    """Same guard for the card builder's slot assignment path."""
    pytest.importorskip("torch")
    import gchat.card_builder.slot_assignment as sa

    base = REPO_ROOT / "research" / "trm" / "h2" / "checkpoints"
    if (
        not (base / "best_model_unified.pt").exists()
        and not (base / "best_model_slot.pt").exists()
    ):
        pytest.skip("no slot-assignment checkpoint available in this environment")

    sa._cached_model = None  # bypass module-level cache
    try:
        model = sa._load_slot_model()
    finally:
        sa._cached_model = None

    assert model is not None, (
        "a slot-assignment checkpoint exists but no model loaded — the card "
        "builder is silently falling back to heuristic content routing"
    )
