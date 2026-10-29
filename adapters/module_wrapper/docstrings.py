"""What a component says about itself, for indexing.

``inspect.getdoc`` walks the MRO, so a pydantic model without its own docstring
reports pydantic's ``BaseModel`` text ("A base class for creating Pydantic
models..."), and a ``str`` enum reports ``str.__doc__``. In ``qdrant_client.models``
that is 249 of 392 classes: every one indexed under the same boilerplate, which no
query can tell apart.

``describe_component`` keeps a class's own docstring and, when there is none,
describes the class from its structure instead: pydantic fields with their
descriptions, enum members, or dataclass fields. Functions keep ``inspect.getdoc``.
"""

from __future__ import annotations

import dataclasses
import enum
import inspect
import re
import types
import typing
from typing import Any

_MAX_FIELDS = 12


def _own_class_doc(cls: type) -> str:
    doc = cls.__dict__.get("__doc__")
    if not isinstance(doc, str) or not doc.strip():
        return ""
    # Some frameworks copy a base's docstring onto subclasses; that is not the
    # class describing itself.
    for base in cls.__mro__[1:]:
        if base.__dict__.get("__doc__") == doc:
            return ""
    if dataclasses.is_dataclass(cls) and doc.startswith(f"{cls.__name__}("):
        # dataclass's auto-generated signature, not prose.
        return ""
    return inspect.cleandoc(doc)


def _type_name(annotation: Any) -> str:
    """Compact, readable type: ``Optional[Filter]`` not the dotted ``Annotated`` form."""
    if annotation is None or annotation is type(None):
        return "None"
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Annotated:
        return _type_name(args[0])
    if origin is typing.Literal:
        return " | ".join(repr(a) for a in args)
    if origin in (typing.Union, types.UnionType):
        names = [_type_name(a) for a in args if a is not type(None)]
        return " | ".join(dict.fromkeys(names))
    if origin is not None:
        base = getattr(origin, "__name__", str(origin))
        inner = ", ".join(_type_name(a) for a in args)
        return f"{base}[{inner}]" if inner else base
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def _structural_doc(cls: type) -> str:
    if issubclass(cls, enum.Enum):
        members = [str(m.value) for m in list(cls)[:_MAX_FIELDS]]
        return f"One of: {', '.join(members)}." if members else ""

    model_fields = getattr(cls, "model_fields", None)
    if isinstance(model_fields, dict) and model_fields:
        parts = []
        public = [(n, f) for n, f in model_fields.items() if not n.startswith("_")]
        if not public:
            return ""
        for name, field in public[:_MAX_FIELDS]:
            part = f"{name} ({_type_name(getattr(field, 'annotation', None))})"
            desc = (getattr(field, "description", None) or "").strip()
            if desc:
                part += f": {' '.join(desc.split())}"
            parts.append(part)
        return "Fields: " + "; ".join(parts) + "."

    if dataclasses.is_dataclass(cls):
        fields = [f for f in dataclasses.fields(cls) if not f.name.startswith("_")]
        if not fields:
            return ""
        fields = fields[:_MAX_FIELDS]
        return (
            "Fields: "
            + "; ".join(f"{f.name} ({_type_name(f.type)})" for f in fields)
            + "."
        )
    return ""


def describe_component(obj: Any) -> str:
    """Docstring to index for ``obj``: its own, else one derived from its structure."""
    try:
        if inspect.isclass(obj):
            return _own_class_doc(obj) or _structural_doc(obj)
        return inspect.getdoc(obj) or ""
    except Exception:
        return ""


def split_camel(name: str) -> str:
    """``HnswConfigDiff`` -> ``Hnsw Config Diff`` (names carry meaning for dense models)."""
    return " ".join(re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", name))


def description_text(name: str, docstring: str, max_chars: int = 500) -> str:
    """Text embedded into a class point's ``description`` vector."""
    doc = " ".join((docstring or "").split())[:max_chars]
    return f"{split_camel(name)}. {doc}".strip()
