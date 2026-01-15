"""DEPRECATED: Chat App Development tool tests.

These tests cover Chat App Development tools (service-account based bot/app
builder workflows) which are not part of the supported core tool surface for
this repository's client test suite.

We keep this file as a placeholder so future re-introduction of Chat App Dev
tools can re-enable tests explicitly.
"""

import pytest

pytest.skip(
    "Chat App Development tools are out of scope for this repo; skipping legacy tests.",
    allow_module_level=True,
)
