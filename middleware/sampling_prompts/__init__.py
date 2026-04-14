"""Sampling validation agent prompt builders.

Each module exports a `get_validation_prompt(tool_args: dict) -> str` function
that builds a domain-expert system prompt for semantic validation of the
calling LLM's structured input before the target tool executes.
"""

from middleware.sampling_prompts.card_dsl import get_card_validation_prompt
from middleware.sampling_prompts.email_dsl import get_email_validation_prompt
from middleware.sampling_prompts.qdrant_query import get_qdrant_validation_prompt
from middleware.sampling_prompts.template_macro import (
    get_template_macro_validation_prompt,
)

__all__ = [
    "get_card_validation_prompt",
    "get_email_validation_prompt",
    "get_qdrant_validation_prompt",
    "get_template_macro_validation_prompt",
]
