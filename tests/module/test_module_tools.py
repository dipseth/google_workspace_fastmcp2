"""Bring-your-own-module tools: module gate, data-only building, JSON output."""

import subprocess
from types import SimpleNamespace
from typing import Optional

import pytest
from pydantic import BaseModel

from adapters.module_wrapper.dsl_builder import DSLObjectBuilder, is_data_class
from adapters.module_wrapper.dsl_parser import DSLParser
from tools.module_tools import check_module_allowed, field_signature, to_jsonable


class Match(BaseModel):
    value: int


class Condition(BaseModel):
    key: str
    match: Optional[Match] = None


class Rule(BaseModel):
    must: list[Condition] = []


SYMBOLS = {"Rule": "ƒ", "Condition": "ʄ", "Match": "☆", "Popen": "Ꝑ"}
OBJS = {"Rule": Rule, "Condition": Condition, "Match": Match, "Popen": subprocess.Popen}


class FakeWrapper:
    def __init__(self):
        self.symbol_mapping = SYMBOLS
        self.components = {
            f"m.{n}": SimpleNamespace(name=n, obj=o, full_path=f"m.{n}")
            for n, o in OBJS.items()
        }

    def get_dsl_parser(self):
        return DSLParser(
            symbol_mapping=SYMBOLS,
            reverse_mapping={v: k for k, v in SYMBOLS.items()},
        )


def test_nested_dsl_builds_real_objects():
    obj = DSLObjectBuilder(FakeWrapper(), data_only=True).parse_and_build(
        'ƒ{must=[ʄ{key="tool", match=☆{value=3}}]}'
    )
    assert obj == Rule(must=[Condition(key="tool", match=Match(value=3))])
    assert to_jsonable(obj) == {"must": [{"key": "tool", "match": {"value": 3}}]}


def test_data_only_refuses_non_data_classes():
    with pytest.raises(ValueError, match="not a data class"):
        DSLObjectBuilder(FakeWrapper(), data_only=True).parse_and_build(
            'Ꝑ{args=["true"]}'
        )


def test_is_data_class():
    assert is_data_class(Rule)
    assert not is_data_class(subprocess.Popen)
    assert not is_data_class(len)


@pytest.mark.parametrize("name", ["os", "subprocess", "json.decoder", "a;b", "x y"])
def test_stdlib_and_junk_refused(name):
    assert check_module_allowed(name)


def test_allowlist(monkeypatch):
    monkeypatch.setenv("MODULE_TOOLS_ALLOWED", "openai.types, decision_pipeline")
    assert check_module_allowed("openai.types") is None
    assert check_module_allowed("decision_pipeline.spec") is None
    assert check_module_allowed("openai") is not None
    assert check_module_allowed("anthropic.types") is not None


def test_no_allowlist_allows_installed_packages(monkeypatch):
    monkeypatch.delenv("MODULE_TOOLS_ALLOWED", raising=False)
    assert check_module_allowed("qdrant_client.models") is None


def test_field_signature():
    assert field_signature(Condition) == {"key": "str", "match": "Match"}
