"""
Mixin Dependency Contracts

Lightweight infrastructure for declaring, validating, and visualizing
cross-mixin dependencies in the ModuleWrapper system.

Each mixin declares:
    _MIXIN_PROVIDES: frozenset[str]  — attributes/methods it creates
    _MIXIN_REQUIRES: frozenset[str]  — attributes/methods it needs from other mixins
    _MIXIN_INIT_ORDER: int           — initialization order (lower = earlier)

These are inert metadata — zero overhead at runtime unless validation
is explicitly triggered.

Usage:
    from adapters.module_wrapper.mixin_meta import (
        validate_mixin_dependencies,
        generate_mermaid_dependency_graph,
    )

    # Static check (no instance needed)
    issues = validate_mixin_dependencies(ModuleWrapper)

    # Runtime check (after initialize())
    issues = check_runtime_dependencies(wrapper_instance)

    # Generate Mermaid diagram
    print(generate_mermaid_dependency_graph(ModuleWrapper))
"""

import functools
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple, Type

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MixinContract:
    """Describes a mixin's dependency contract."""

    name: str
    provides: FrozenSet[str]
    requires: FrozenSet[str]
    init_order: int


def _get_mixin_classes(cls: Type) -> List[Type]:
    """Extract mixin classes from the MRO (excluding object)."""
    return [c for c in cls.__mro__ if c is not object and c is not cls]


def _extract_contract(mixin_cls: Type) -> Optional[MixinContract]:
    """Extract the dependency contract from a mixin class, if declared."""
    provides = getattr(mixin_cls, "_MIXIN_PROVIDES", None)
    requires = getattr(mixin_cls, "_MIXIN_REQUIRES", None)
    init_order = getattr(mixin_cls, "_MIXIN_INIT_ORDER", None)

    if provides is None and requires is None:
        return None

    return MixinContract(
        name=mixin_cls.__name__,
        provides=frozenset(provides) if provides else frozenset(),
        requires=frozenset(requires) if requires else frozenset(),
        init_order=init_order if init_order is not None else 999,
    )


def get_all_contracts(cls: Type) -> Dict[str, MixinContract]:
    """Get contracts for all mixins in the MRO that have declarations.

    Only includes classes that define their own _MIXIN_PROVIDES (not inherited).

    Args:
        cls: The composed class (e.g. ModuleWrapper)

    Returns:
        Dict mapping class name to MixinContract
    """
    contracts = {}

    # Check the class itself (only if it has its own declarations)
    if "_MIXIN_PROVIDES" in cls.__dict__:
        contract = _extract_contract(cls)
        if contract is not None:
            contracts[contract.name] = contract

    # Check all parent classes in MRO
    for mixin_cls in _get_mixin_classes(cls):
        if "_MIXIN_PROVIDES" in mixin_cls.__dict__:
            contract = _extract_contract(mixin_cls)
            if contract is not None:
                contracts[contract.name] = contract

    return contracts


def validate_mixin_dependencies(cls: Type) -> List[str]:
    """Static check: all requires satisfied by some provides in MRO.

    Args:
        cls: The composed class (e.g. ModuleWrapper)

    Returns:
        List of issue descriptions. Empty list = all good.
    """
    contracts = get_all_contracts(cls)
    issues = []

    if not contracts:
        issues.append(f"{cls.__name__}: no mixin contracts found in MRO")
        return issues

    # Collect all provided attributes across all mixins
    all_provides: Set[str] = set()
    for contract in contracts.values():
        all_provides.update(contract.provides)

    # Check each mixin's requirements
    for name, contract in contracts.items():
        unsatisfied = contract.requires - all_provides
        if unsatisfied:
            issues.append(
                f"{name} requires {sorted(unsatisfied)} but no mixin provides them"
            )

    # Check for init order conflicts: a mixin requiring something
    # from a higher-order mixin suggests an init ordering issue
    for name, contract in contracts.items():
        for req in contract.requires:
            # Find which mixin provides this
            for provider_name, provider_contract in contracts.items():
                if req in provider_contract.provides:
                    if provider_contract.init_order > contract.init_order:
                        issues.append(
                            f"{name} (order={contract.init_order}) requires "
                            f"'{req}' from {provider_name} "
                            f"(order={provider_contract.init_order}) — "
                            f"provider initializes later"
                        )
                    break

    return issues


def check_runtime_dependencies(
    instance: Any, mixin_cls: Optional[Type] = None
) -> List[str]:
    """Runtime check: required attributes are non-None on an instance.

    Args:
        instance: The initialized ModuleWrapper instance
        mixin_cls: Optional specific mixin to check. If None, checks all.

    Returns:
        List of issue descriptions. Empty list = all good.
    """
    issues = []
    cls = type(instance)

    if mixin_cls is not None:
        classes_to_check = [mixin_cls]
    else:
        classes_to_check = [cls] + _get_mixin_classes(cls)

    for klass in classes_to_check:
        contract = _extract_contract(klass)
        if contract is None:
            continue

        for attr in contract.requires:
            if not hasattr(instance, attr):
                issues.append(f"{contract.name}: required attribute '{attr}' missing")
            elif getattr(instance, attr) is None:
                issues.append(f"{contract.name}: required attribute '{attr}' is None")

    return issues


def generate_mermaid_dependency_graph(cls: Type) -> str:
    """Auto-generate a Mermaid diagram from mixin dependency declarations.

    Args:
        cls: The composed class (e.g. ModuleWrapper)

    Returns:
        Mermaid graph definition string
    """
    contracts = get_all_contracts(cls)
    if not contracts:
        return "graph TD\n    NO_CONTRACTS[No mixin contracts found]"

    # Sort by init order
    sorted_contracts = sorted(contracts.values(), key=lambda c: c.init_order)

    lines = ["graph TD"]

    # Add node definitions with init order
    for contract in sorted_contracts:
        provides_count = len(contract.provides)
        requires_count = len(contract.requires)
        label = (
            f"{contract.name}\\n"
            f"order={contract.init_order}\\n"
            f"+{provides_count} provides / -{requires_count} requires"
        )
        lines.append(f'    {contract.name}["{label}"]')

    lines.append("")

    # Build a provides→mixin index for edge creation
    provides_index: Dict[str, str] = {}
    for contract in sorted_contracts:
        for attr in contract.provides:
            provides_index[attr] = contract.name

    # Add edges (requires → provides)
    seen_edges: Set[Tuple[str, str]] = set()
    for contract in sorted_contracts:
        for req in contract.requires:
            provider = provides_index.get(req)
            if provider and provider != contract.name:
                edge = (provider, contract.name)
                if edge not in seen_edges:
                    seen_edges.add(edge)
                    lines.append(f"    {provider} --> {contract.name}")

    # Style the root node
    root = sorted_contracts[0] if sorted_contracts else None
    if root:
        lines.append("")
        lines.append(f"    style {root.name} fill:#e1f5fe")

    return "\n".join(lines)


def generate_provides_requires_table(cls: Type) -> str:
    """Generate a markdown table of mixin contracts.

    Args:
        cls: The composed class (e.g. ModuleWrapper)

    Returns:
        Markdown table string
    """
    contracts = get_all_contracts(cls)
    if not contracts:
        return "No mixin contracts found."

    sorted_contracts = sorted(contracts.values(), key=lambda c: c.init_order)

    lines = [
        "| Mixin | Order | Provides | Requires |",
        "|-------|-------|----------|----------|",
    ]

    for contract in sorted_contracts:
        provides = ", ".join(sorted(contract.provides)) or "(none)"
        requires = ", ".join(sorted(contract.requires)) or "(none)"
        lines.append(
            f"| {contract.name} | {contract.init_order} | {provides} | {requires} |"
        )

    return "\n".join(lines)


def requires_deps(*attrs: str):
    """Decorator for strict-mode runtime checks on critical methods.

    When MODULE_WRAPPER_STRICT=1, validates that required attributes
    are present and non-None before method execution.

    Usage:
        @requires_deps("client", "embedder")
        def search(self, query):
            ...
    """
    import os

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            if os.environ.get("MODULE_WRAPPER_STRICT") == "1":
                for attr in attrs:
                    val = getattr(self, attr, None)
                    if val is None:
                        raise RuntimeError(
                            f"{type(self).__name__}.{fn.__name__}() requires "
                            f"'{attr}' but it is None. "
                            f"Ensure initialization order is correct."
                        )
            return fn(self, *args, **kwargs)

        return wrapper

    return decorator
