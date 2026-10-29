"""Build real objects from parameterized DSL, for any wrapped module.

Walks the DSLNode tree produced by ``DSLParser`` and instantiates each node's class
from the wrapper's component registry, recursing into nested nodes and lists::

    builder = DSLObjectBuilder(wrapper)
    builder.parse_and_build('¶{minEffect=0.1, n=100}')   # -> decision_pipeline.Plan

``data_only=True`` restricts construction to data classes (pydantic models,
dataclasses, enums). Use it whenever the module or the DSL comes from a client:
constructing an arbitrary class can run arbitrary code (``subprocess.Popen{...}``).
"""

from __future__ import annotations

import dataclasses
import enum
from typing import TYPE_CHECKING, Any, List

from adapters.module_wrapper.dsl_parser import DSLNode, DSLParseResult

if TYPE_CHECKING:
    from adapters.module_wrapper.core import ModuleWrapper


def is_data_class(cls: Any) -> bool:
    """Pydantic model, dataclass or enum: constructing it only stores values."""
    if not isinstance(cls, type):
        return False
    if issubclass(cls, enum.Enum) or dataclasses.is_dataclass(cls):
        return True
    try:
        from pydantic import BaseModel

        return issubclass(cls, BaseModel)
    except ImportError:  # pragma: no cover - pydantic is a hard dependency
        return False


class DSLObjectBuilder:
    """Builds objects of a wrapped module from parsed DSL trees."""

    def __init__(self, wrapper: "ModuleWrapper", data_only: bool = False):
        self.wrapper = wrapper
        self.parser = wrapper.get_dsl_parser()
        self.data_only = data_only

    def parse_dsl(self, dsl: str) -> DSLParseResult:
        return self.parser.parse(dsl)

    def parse_and_build(self, dsl: str) -> Any:
        """Parse ``dsl`` and build its first root node."""
        result = self.parse_dsl(dsl)
        if not result.root_nodes:
            raise ValueError(f"DSL produced no nodes: {dsl!r} ({result.issues})")
        return self.build(result.root_nodes[0])

    def build(self, node: DSLNode) -> Any:
        """Recursively instantiate ``node`` and its nested nodes."""
        cls = self._resolve_class(node.component_name)
        kwargs = {key: self._build_value(value) for key, value in node.params.items()}
        try:
            return cls(**kwargs)
        except Exception as e:
            raise ValueError(
                f"Failed to instantiate {node.component_name}(**{kwargs}): {e}"
            ) from e

    def build_all(self, nodes: List[DSLNode]) -> List[Any]:
        return [self.build(node) for node in nodes]

    def _build_value(self, value: Any) -> Any:
        if isinstance(value, DSLNode):
            return self.build(value)
        if isinstance(value, list):
            return [self._build_value(item) for item in value]
        if isinstance(value, dict):
            return {k: self._build_value(v) for k, v in value.items()}
        return value

    def _resolve_class(self, component_name: str) -> type:
        """Component name -> its object in the wrapped module."""
        for comp in self.wrapper.components.values():
            if comp.name == component_name and comp.obj is not None:
                if self.data_only and not is_data_class(comp.obj):
                    raise ValueError(
                        f"'{component_name}' is not a data class (pydantic model, "
                        "dataclass or enum); only data classes can be built here."
                    )
                return comp.obj
        names = sorted({c.name for c in self.wrapper.components.values()})
        raise ValueError(
            f"Unknown component: '{component_name}'. Available: {names[:20]}"
        )
