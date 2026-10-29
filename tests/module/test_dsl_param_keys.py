"""A word followed by "=" is always a parameter key, never a symbol or component."""

from adapters.module_wrapper.dsl_parser import DSLParser

SYMBOLS = {"Plan": "¶", "date": "đ", "Filter": "ƒ"}


def _params(dsl):
    parser = DSLParser(
        symbol_mapping=SYMBOLS, reverse_mapping={v: k for k, v in SYMBOLS.items()}
    )
    nodes = parser.parse(dsl).root_nodes
    return nodes[0].component_name, nodes[0].params


def test_single_letter_key_kept():
    assert _params("¶{minEffect=0.1, n=100}") == (
        "Plan",
        {"minEffect": 0.1, "n": 100},
    )


def test_key_named_like_a_component_stays_a_key():
    assert _params('¶{date="2026-10-29", n=3}')[1] == {"date": "2026-10-29", "n": 3}


def test_symbol_after_equals_still_builds_nested_node():
    name, params = _params("ƒ{must=[¶{n=1}]}")
    assert name == "Filter"
    assert params["must"][0].component_name == "Plan"
    assert params["must"][0].params == {"n": 1}
