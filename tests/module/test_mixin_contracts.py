"""
Tests for mixin dependency contracts.

These tests validate the _MIXIN_PROVIDES / _MIXIN_REQUIRES / _MIXIN_INIT_ORDER
declarations on all mixins, ensuring the dependency graph is consistent.

No Qdrant connection needed — these are pure static checks.
"""

import pytest

from adapters.module_wrapper import ModuleWrapper
from adapters.module_wrapper.cache_mixin import CacheMixin
from adapters.module_wrapper.core import ModuleWrapperBase
from adapters.module_wrapper.embedding_mixin import EmbeddingMixin
from adapters.module_wrapper.graph_mixin import GraphMixin
from adapters.module_wrapper.indexing_mixin import IndexingMixin
from adapters.module_wrapper.instance_pattern_mixin import InstancePatternMixin
from adapters.module_wrapper.mixin_meta import (
    MixinContract,
    generate_mermaid_dependency_graph,
    generate_provides_requires_table,
    get_all_contracts,
    validate_mixin_dependencies,
)
from adapters.module_wrapper.pipeline_mixin import PipelineMixin
from adapters.module_wrapper.qdrant_mixin import QdrantMixin
from adapters.module_wrapper.relationships_mixin import RelationshipsMixin
from adapters.module_wrapper.search_mixin import SearchMixin
from adapters.module_wrapper.skills_mixin import SkillsMixin
from adapters.module_wrapper.symbols_mixin import SymbolsMixin

ALL_MIXINS = [
    ModuleWrapperBase,
    QdrantMixin,
    EmbeddingMixin,
    IndexingMixin,
    RelationshipsMixin,
    SearchMixin,
    SymbolsMixin,
    GraphMixin,
    CacheMixin,
    PipelineMixin,
    SkillsMixin,
    InstancePatternMixin,
]


class TestMixinDeclarations:
    """Every mixin must have _MIXIN_PROVIDES, _MIXIN_REQUIRES, _MIXIN_INIT_ORDER."""

    @pytest.mark.parametrize("mixin_cls", ALL_MIXINS, ids=lambda c: c.__name__)
    def test_has_provides(self, mixin_cls):
        assert hasattr(mixin_cls, "_MIXIN_PROVIDES"), (
            f"{mixin_cls.__name__} missing _MIXIN_PROVIDES"
        )
        assert isinstance(mixin_cls._MIXIN_PROVIDES, frozenset)

    @pytest.mark.parametrize("mixin_cls", ALL_MIXINS, ids=lambda c: c.__name__)
    def test_has_requires(self, mixin_cls):
        assert hasattr(mixin_cls, "_MIXIN_REQUIRES"), (
            f"{mixin_cls.__name__} missing _MIXIN_REQUIRES"
        )
        assert isinstance(mixin_cls._MIXIN_REQUIRES, frozenset)

    @pytest.mark.parametrize("mixin_cls", ALL_MIXINS, ids=lambda c: c.__name__)
    def test_has_init_order(self, mixin_cls):
        assert hasattr(mixin_cls, "_MIXIN_INIT_ORDER"), (
            f"{mixin_cls.__name__} missing _MIXIN_INIT_ORDER"
        )
        assert isinstance(mixin_cls._MIXIN_INIT_ORDER, int)

    @pytest.mark.parametrize("mixin_cls", ALL_MIXINS, ids=lambda c: c.__name__)
    def test_provides_not_empty(self, mixin_cls):
        assert len(mixin_cls._MIXIN_PROVIDES) > 0, (
            f"{mixin_cls.__name__} has empty _MIXIN_PROVIDES"
        )


class TestDependencySatisfaction:
    """All requires must be satisfied by some provides in the MRO."""

    def test_all_requires_satisfied(self):
        issues = validate_mixin_dependencies(ModuleWrapper)
        # Filter to only unsatisfied-requires issues (not init-order warnings)
        unsatisfied = [i for i in issues if "but no mixin provides them" in i]
        assert unsatisfied == [], f"Unsatisfied dependencies:\n" + "\n".join(
            unsatisfied
        )

    def test_no_self_dependency(self):
        """No mixin should require something it provides itself."""
        contracts = get_all_contracts(ModuleWrapper)
        for name, contract in contracts.items():
            overlap = contract.provides & contract.requires
            assert overlap == set(), f"{name} both provides and requires: {overlap}"


class TestInitOrder:
    """Init order should be consistent across all mixins."""

    def test_unique_or_shared_init_orders(self):
        """Init orders can be shared (parallel mixins) but must be valid ints."""
        contracts = get_all_contracts(ModuleWrapper)
        for name, contract in contracts.items():
            assert isinstance(contract.init_order, int), (
                f"{name} has non-int init_order: {contract.init_order}"
            )

    def test_base_has_lowest_order(self):
        contracts = get_all_contracts(ModuleWrapper)
        base = contracts.get("ModuleWrapperBase")
        assert base is not None
        for name, contract in contracts.items():
            if name != "ModuleWrapperBase":
                assert contract.init_order >= base.init_order, (
                    f"{name} (order={contract.init_order}) has lower order "
                    f"than base (order={base.init_order})"
                )

    def test_qdrant_before_indexing(self):
        """QdrantMixin must init before IndexingMixin."""
        contracts = get_all_contracts(ModuleWrapper)
        assert (
            contracts["QdrantMixin"].init_order < contracts["IndexingMixin"].init_order
        )

    def test_embedding_before_indexing(self):
        """EmbeddingMixin must init before IndexingMixin."""
        contracts = get_all_contracts(ModuleWrapper)
        assert (
            contracts["EmbeddingMixin"].init_order
            < contracts["IndexingMixin"].init_order
        )


class TestProvidesCorrespondToReal:
    """Provided names should correspond to actual methods/attributes on the class."""

    @staticmethod
    def _get_init_assigned_attrs(cls) -> set:
        """Extract attribute names assigned in __init__ via source inspection."""
        import inspect
        import re

        attrs = set()
        for klass in cls.__mro__:
            if klass is object:
                continue
            if "__init__" not in klass.__dict__:
                continue
            try:
                source = inspect.getsource(klass.__init__)
                # Match self.xxx = patterns (captures the attribute name)
                for match in re.finditer(r"self\.(\w+)\s*[:=]", source):
                    attrs.add(match.group(1))
            except (OSError, TypeError):
                pass
        return attrs

    @pytest.mark.parametrize("mixin_cls", ALL_MIXINS, ids=lambda c: c.__name__)
    def test_provides_exist_on_class(self, mixin_cls):
        """Each provided name should be findable in class dict or __init__."""
        init_attrs = self._get_init_assigned_attrs(ModuleWrapper)
        missing = []
        for attr in mixin_cls._MIXIN_PROVIDES:
            # Check class-level definitions across the full MRO
            found = False
            for klass in ModuleWrapper.__mro__:
                if attr in klass.__dict__:
                    found = True
                    break
            # Also accept attrs assigned in __init__ (instance attributes)
            if not found and attr in init_attrs:
                found = True
            if not found:
                missing.append(attr)

        assert missing == [], (
            f"{mixin_cls.__name__} declares provides not found in MRO: {missing}"
        )


class TestMermaidGeneration:
    """Mermaid diagram generation works without errors."""

    def test_generates_mermaid(self):
        diagram = generate_mermaid_dependency_graph(ModuleWrapper)
        assert diagram.startswith("graph TD")
        assert "ModuleWrapperBase" in diagram

    def test_generates_table(self):
        table = generate_provides_requires_table(ModuleWrapper)
        assert "| Mixin |" in table
        assert "ModuleWrapperBase" in table

    def test_all_mixins_in_diagram(self):
        diagram = generate_mermaid_dependency_graph(ModuleWrapper)
        contracts = get_all_contracts(ModuleWrapper)
        for name in contracts:
            assert name in diagram, f"{name} missing from Mermaid diagram"

    def test_contract_extraction(self):
        contracts = get_all_contracts(ModuleWrapper)
        assert len(contracts) >= len(ALL_MIXINS), (
            f"Expected at least {len(ALL_MIXINS)} contracts, got {len(contracts)}"
        )
        for name, contract in contracts.items():
            assert isinstance(contract, MixinContract)
            assert isinstance(contract.provides, frozenset)
            assert isinstance(contract.requires, frozenset)
