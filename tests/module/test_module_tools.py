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


ENTRIES = [
    {"name": "NoulQuestion", "description": "A yes/no question"},
    {"name": "ChoiceQuestion", "description": "Pick one option"},
]


def test_jev_rerank_off_without_key(monkeypatch):
    from tools.module_tools import jev_rerank

    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert jev_rerank("pick one", ENTRIES) is None


def test_jev_rerank_reads_choice_probabilities(monkeypatch):
    import httpx

    from tools.module_tools import jev_rerank

    sent = {}

    def fake_post(url, json, headers, timeout):
        sent.update(url=url, body=json)
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "answers": {
                    "component": {
                        "type": "choice",
                        "choice": "ChoiceQuestion",
                        "confidence": 0.9,
                        "probabilities": {"NoulQuestion": 0.1, "ChoiceQuestion": 0.9},
                    }
                }
            },
        )

    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(httpx, "post", fake_post)
    assert jev_rerank("pick one", ENTRIES) == [0.1, 0.9]
    q = sent["body"]["questions"]["component"]
    assert q["type"] == "choice"
    assert q["criteria"] == {
        "NoulQuestion": "A yes/no question",
        "ChoiceQuestion": "Pick one option",
    }
    assert sent["url"].endswith("/v1/systemone")


def test_jev_rerank_error_keeps_pool_order(monkeypatch):
    import httpx

    from tools.module_tools import jev_rerank

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(httpx, "post", boom)
    assert jev_rerank("pick one", ENTRIES) is None
