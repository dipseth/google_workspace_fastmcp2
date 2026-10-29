"""describe_component: own docstrings, never inherited boilerplate."""

import dataclasses
import enum
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

from adapters.module_wrapper.docstrings import describe_component


class Documented(BaseModel):
    """Retry policy for outbound calls."""

    attempts: int = 3


class Undocumented(BaseModel):
    capacity_mb: Optional[int] = Field(None, description="Size of one segment in MB")
    mode: Literal["fast", "safe"] = "fast"
    tag: Annotated[str, "meta"] = ""


class Color(str, enum.Enum):
    RED = "red"
    BLUE = "blue"


@dataclasses.dataclass
class Point:
    x: int
    y: int


def test_own_docstring_kept():
    assert describe_component(Documented) == "Retry policy for outbound calls."


def test_inherited_pydantic_docstring_replaced_by_fields():
    doc = describe_component(Undocumented)
    assert "Pydantic" not in doc
    assert "capacity_mb (int): Size of one segment in MB" in doc
    assert "mode ('fast' | 'safe')" in doc
    assert "tag (str)" in doc


def test_str_enum_lists_members_not_str_doc():
    assert describe_component(Color) == "One of: red, blue."


def test_dataclass_auto_signature_replaced_by_fields():
    assert describe_component(Point) == "Fields: x (int); y (int)."


def test_function_docstring_unchanged():
    def f():
        """Does a thing."""

    assert describe_component(f) == "Does a thing."
