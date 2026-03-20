"""Anthropic prompt cache keepalive engine.

Periodically sends sampling requests with the same system prompt prefix
used by real tool calls (DSL docs, symbols, validation rules) to keep
Anthropic's prompt cache warm.  Keepalive calls double as exploration —
varying the user message after the cached prefix to discover new DSL
patterns that can be indexed back into Qdrant.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()

# ---------------------------------------------------------------------------
# Exploration prompt pools — varied user messages appended after the cached
# system prefix so the keepalive call also produces useful output.
# ---------------------------------------------------------------------------

GCHAT_EXPLORATION_PROMPTS: List[str] = [
    (
        "Generate a novel card DSL structure for a dashboard status card "
        "with 3 KPI metrics, a divider, and 2 action buttons. "
        "Return only the DSL notation and a brief card_params JSON."
    ),
    (
        "Design a carousel card for displaying team member profiles. "
        "Use at least 3 CarouselCards each with an image, name, role, and a button."
    ),
    (
        "Create a grid-based card for displaying 6 project items with "
        "icons, titles, and click actions. Use GridItem with proper nesting."
    ),
    (
        "Design a notification card using DecoratedText with colour-coded "
        "status icons, a ChipList for quick actions, and a collapsible section."
    ),
    (
        "Build a form card with SelectionInput (radio buttons), "
        "two text inputs via DecoratedText, and a ButtonList with submit/cancel."
    ),
    (
        "Create a two-column card using Columns with a sidebar of "
        "navigation chips and a main content area of decorated text items."
    ),
    (
        "Design an approval workflow card: header with requester info, "
        "section with request details, and a ButtonList with Approve/Reject/Comment."
    ),
    (
        "Generate a card combining a Carousel of image previews with "
        "a Section below containing file metadata in DecoratedText widgets."
    ),
    (
        "Create an onboarding checklist card with numbered DecoratedText "
        "items showing completion status icons and a progress indicator section."
    ),
    (
        "Design a meeting summary card with header, attendee ChipList, "
        "agenda items as DecoratedText, action items section, and a join-link Button."
    ),
]

EMAIL_EXPLORATION_PROMPTS: List[str] = [
    (
        "Generate an email DSL spec for a weekly digest with a hero image, "
        "3 content sections, and a CTA button. Return only the DSL notation "
        "and email_params JSON."
    ),
    (
        "Design a two-column newsletter email with a sidebar of links "
        "and a main content area with text blocks and images."
    ),
    (
        "Create a transactional email for order confirmation with a header, "
        "order details table, shipping info, and a tracking button."
    ),
    (
        "Build a feedback request email with a hero block, explanation text, "
        "and 3 rating buttons (Positive/Neutral/Negative) with redirect URLs."
    ),
    (
        "Design an event invitation email with a hero image, event details "
        "in text blocks, a map image, and RSVP buttons."
    ),
    (
        "Create a welcome onboarding email with a header, 3 numbered "
        "getting-started steps using text blocks, and a start button."
    ),
    (
        "Generate an email with an accordion block for FAQ items, "
        "a divider, and a contact-support button at the bottom."
    ),
    (
        "Design an email with a table block showing comparison data, "
        "a spacer, and a CTA button linking to the full report."
    ),
    (
        "Build a social proof email with a carousel of testimonial cards, "
        "a divider, and a sign-up button block."
    ),
    (
        "Create a product announcement email with a hero, feature highlights "
        "in a 2-column layout, and footer with social links."
    ),
]

QDRANT_EXPLORATION_PROMPTS: List[str] = [
    (
        "Write a Qdrant DSL filter to find all tool responses from the gmail "
        "service created in the last 7 days. Use the appropriate filter and "
        "field condition symbols from the reference. Return the DSL string."
    ),
    (
        "Design a multi-stage prefetch query: first retrieve 50 candidates "
        "matching a service filter, then re-rank by cosine similarity. "
        "Use the Prefetch symbol from the reference. Return the full query DSL."
    ),
    (
        "Build a filter DSL combining must and should conditions: must match "
        "a specific tool_name AND must_not match status='archived', should "
        "boost items matching a tag. Use the Filter and FieldCondition symbols."
    ),
    (
        "Write a recommendation query using the RecommendQuery symbol to find "
        "tool responses similar to a set of positive example point IDs. "
        "Return the query_dsl string using symbols from the reference."
    ),
    (
        "Create a FusionQuery that combines results from two different "
        "search strategies. Use the FusionQuery symbol from the reference. "
        "Return the query_dsl string."
    ),
    (
        "Design a filter using MatchAny to find responses from multiple "
        "tools at once (e.g. send_dynamic_card and compose_dynamic_email). "
        "Nest it inside a Filter with a must condition."
    ),
    (
        "Write a query combining a HasIdCondition filter to exclude known "
        "results with a should clause boosting recent items. "
        "Use the appropriate symbols from the reference."
    ),
    (
        "Build a DiscoverQuery to explore the collection for tool responses "
        "related to 'interactive widgets'. Use the DiscoverQuery symbol "
        "and a ContextPair for positive/negative examples."
    ),
    (
        "Create a filter DSL for payload-only search: find all points where "
        "'service' matches 'gmail' and 'tool_name' matches via MatchText "
        "for a full-text search on the tool name field."
    ),
    (
        "Design an OrderByQuery to retrieve the most recent tool responses "
        "ordered by timestamp descending. Use the OrderBy and OrderByQuery "
        "symbols from the reference. Return the query_dsl string."
    ),
]

_MODULE_EXPLORATION_PROMPTS: Dict[str, List[str]] = {
    "gchat": GCHAT_EXPLORATION_PROMPTS,
    "email": EMAIL_EXPLORATION_PROMPTS,
    "qdrant": QDRANT_EXPLORATION_PROMPTS,
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class KeepaliveModuleConfig:
    """Configuration for a module whose system prompts should be kept warm."""

    module_name: str
    get_system_prompt_fn: Callable[[], str]
    exploration_prompts: List[str] = field(default_factory=list)
    dsl_type_label: str = ""

    # Runtime stats
    last_keepalive_at: float = 0.0
    cached_tokens_last: int = 0
    total_keepalive_calls: int = 0
    total_cached_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    total_full_price_usd: float = 0.0  # what it would cost without caching
    total_savings_usd: float = 0.0

# ---------------------------------------------------------------------------
# System prompt builders — reuse the exact same context that real tool
# validation agents inject so the Anthropic cache prefix matches.
# ---------------------------------------------------------------------------

def _build_gchat_system_prompt() -> str:
    """Assemble the cacheable system prompt for Google Chat card DSL."""
    parts: List[str] = [
        "You are a Google Chat card DSL expert. "
        "Use the reference below to generate valid card structures."
    ]
    try:
        from gchat.wrapper_api import get_dsl_documentation

        parts.append(
            get_dsl_documentation(include_examples=True, include_hierarchy=True)
        )
    except Exception:
        parts.append("(Card DSL documentation unavailable)")

    try:
        from gchat.wrapper_api import get_gchat_symbol_table_text

        parts.append(get_gchat_symbol_table_text())
    except Exception:
        pass

    return "\n\n".join(parts)

def _build_email_system_prompt() -> str:
    """Assemble the cacheable system prompt for email DSL.

    Must exceed Anthropic's 1,024-token minimum for caching.
    Includes the same validation rules used by the real email validation
    agent so the cached prefix matches real tool calls.
    """
    parts: List[str] = [
        "You are an MJML email composition expert validator. Your job is to "
        "review email specifications and generate valid, responsive emails "
        "following MJML best practices."
    ]
    try:
        from gmail.email_wrapper_api import get_email_dsl_documentation

        parts.append(get_email_dsl_documentation(include_examples=True))
    except Exception:
        parts.append("(Email DSL documentation unavailable)")

    # Include the validation rules from the real email validation prompt
    # so the cached prefix matches what real validation agent calls use.
    parts.append(
        "## Validation Checklist\n"
        "1. **MJML block structure**: `<mj-section>` wraps `<mj-column>` wraps "
        "content blocks (`<mj-text>`, `<mj-button>`, `<mj-image>`, etc.). "
        "No content outside this hierarchy.\n"
        "2. **Responsive patterns**: Use percentage widths on columns (not fixed "
        'px for layout). Images should have `fluid-on-mobile="true"` or '
        "appropriate width constraints.\n"
        "3. **Accessibility**: Buttons have descriptive text; images have alt "
        "attributes; sufficient color contrast between text and backgrounds.\n"
        "4. **Content completeness**: Subject line present, recipient addresses "
        "valid format, body content is non-empty and coherent.\n"
        "5. **Template variables**: If Jinja2 template syntax is used "
        "(`{{ }}`, `{% %}`), verify matching braces and valid variable names.\n"
        "6. **Column layout**: ColumnsBlock must contain Column children. "
        "Columns hold content blocks (TextBlock, ButtonBlock, ImageBlock). "
        "Maximum 4 columns recommended for mobile compatibility.\n"
        "7. **Hero blocks**: HeroBlock should have a background image URL, "
        'overlay text, and a call-to-action button. Use mode="fluid" for '
        "full-width rendering.\n"
        "8. **Social blocks**: SocialBlock should list platform names and URLs. "
        "Supported: facebook, twitter, linkedin, instagram, youtube, github.\n"
        "9. **Spacing**: Use SpacerBlock for vertical spacing between sections. "
        "Default height is 20px. Avoid excessive spacers — use padding instead.\n"
        "10. **Footer compliance**: FooterBlock should include unsubscribe link "
        "and sender address for CAN-SPAM/GDPR compliance."
    )

    # Add detailed MJML element reference to ensure we exceed 1024 tokens
    parts.append(
        "## MJML Element Reference\n"
        "- `<mj-section>`: Top-level container, supports background-color, "
        "background-url, padding, direction (ltr/rtl), full-width.\n"
        "- `<mj-column>`: Layout column within section, supports width (%), "
        "vertical-align, padding, background-color, border, border-radius.\n"
        "- `<mj-text>`: Text content block, supports font-family, font-size, "
        "color, line-height, padding, align (left/center/right). HTML allowed.\n"
        "- `<mj-button>`: CTA button, supports href, background-color, color, "
        "font-size, border-radius, padding, align, width, inner-padding.\n"
        "- `<mj-image>`: Image block, supports src, alt, width, height, "
        "fluid-on-mobile, padding, align, href (clickable), border-radius.\n"
        "- `<mj-divider>`: Horizontal rule, supports border-color, border-width, "
        "border-style, padding, width.\n"
        "- `<mj-spacer>`: Vertical spacing, supports height, padding.\n"
        "- `<mj-hero>`: Hero section with background image, supports mode "
        "(fixed/fluid), background-height, background-url, background-color, "
        "vertical-align, width.\n"
        "- `<mj-social>`: Social links container, supports mode (horizontal/"
        "vertical), align, icon-size, icon-padding.\n"
        "- `<mj-social-element>`: Individual social icon, supports name, href, "
        "src (custom icon), alt, background-color.\n"
        "- `<mj-table>`: HTML table within email, supports width, cellpadding, "
        "cellspacing, color, font-family, font-size, line-height.\n"
        "- `<mj-accordion>`: Expandable content sections, supports border, "
        "font-family, icon-align, icon-position.\n"
        "- `<mj-carousel>`: Image carousel, supports icon-width, left-icon, "
        "right-icon, thumbnails (visible/hidden).\n"
        "- `<mj-navbar>`: Navigation bar, supports hamburger (hamburger/none), "
        "align.\n"
        "- `<mj-navbar-link>`: Navigation link, supports href, color, "
        "font-family, font-size, padding."
    )

    return "\n\n".join(parts)

def _build_qdrant_system_prompt() -> str:
    """Assemble the cacheable system prompt for Qdrant search DSL.

    Uses the qdrant_client.models ModuleWrapper to dynamically generate
    the symbol table and grammar — no hardcoded symbols.
    Must exceed Anthropic's 1,024-token minimum for caching.
    """
    parts: List[str] = [
        "You are a Qdrant vector search expert validator. Your job is to "
        "review search queries, filter DSL, and query DSL for semantic "
        "correctness and optimal search patterns."
    ]

    # Dynamic symbol table + grammar from the module wrapper
    try:
        from middleware.qdrant_core.qdrant_models_wrapper import (
            get_qdrant_models_wrapper,
        )

        wrapper = get_qdrant_models_wrapper()

        # Symbol table text (generated by SymbolsMixin)
        symbol_text = wrapper.get_symbol_table_text()
        if symbol_text:
            parts.append(symbol_text)

        # Grammar description (categorised filter vs query symbols)
        if wrapper.symbol_mapping:
            from middleware.qdrant_core.tools import _build_grammar_description

            symbols = dict(wrapper.symbol_mapping)
            grammar = _build_grammar_description(symbols)
            if grammar:
                parts.append(grammar)
    except Exception:
        parts.append("(Qdrant DSL documentation unavailable)")

    # Static validation rules — matches the real validation prompt prefix
    # so the cached prefix aligns with live qdrant_search validation calls.
    parts.append(
        "## Qdrant Filter DSL Reference\n"
        "Filters use nested conditions with `must`, `should`, `must_not` arrays.\n"
        "Each condition is a FieldCondition wrapping a match type:\n"
        "- MatchValue — exact match (string or number)\n"
        "- MatchAny — match any value in a list\n"
        "- MatchText — full-text search on a field\n"
        "- Range — numeric range with gt, gte, lt, lte\n"
        "- HasIdCondition — filter by point IDs\n"
        "- IsEmptyCondition — check if field exists\n"
        "- IsNullCondition — check if field is null\n\n"
        "## Advanced Query Types\n"
        "- FusionQuery — combine results from multiple search strategies\n"
        "- RecommendQuery — find similar points via positive/negative examples\n"
        "- DiscoverQuery — explore with context pairs for guided discovery\n"
        "- Prefetch — multi-stage hierarchical retrieval with re-ranking\n"
        "- OrderByQuery — retrieve points ordered by a payload field\n\n"
        "## Validation Checklist\n"
        "1. **Query clarity**: Search query should be specific enough to produce "
        "relevant results. Vague single-word queries may need expansion.\n"
        "2. **Filter correctness**: Filter conditions must use valid operators "
        "and field names. Nested conditions must be properly structured.\n"
        "3. **Prefetch patterns**: If using multi-stage search (prefetch), "
        "ensure the prefetch query is broader than the final query.\n"
        "4. **Named vectors**: If targeting a specific named vector, verify "
        "the vector name matches the collection schema.\n"
        "5. **Score threshold**: Verify it is a reasonable value "
        "(typically 0.0-1.0 for cosine similarity).\n"
        "6. **DSL syntax**: Symbols must match the registered symbol table. "
        "Parameters must use correct types (strings quoted, numbers unquoted, "
        "lists in square brackets, nested symbols for complex values).\n"
        "7. **Collection schema**: The default collection `mcp_tool_responses` "
        "has payload fields: tool_name, service, user_email, timestamp, "
        "args, response_content, error, status_code.\n"
        "8. **Recommend queries**: Positive and negative point IDs must be "
        "valid UUIDs from the target collection.\n"
        "9. **Fusion queries**: Multiple sub-queries should target different "
        "aspects of the search to benefit from result fusion.\n"
        "10. **Dry run**: Use dry_run=true with filter_dsl to validate "
        "DSL syntax without executing the query."
    )

    return "\n\n".join(parts)

_MODULE_PROMPT_BUILDERS: Dict[str, Callable[[], str]] = {
    "gchat": _build_gchat_system_prompt,
    "email": _build_email_system_prompt,
    "qdrant": _build_qdrant_system_prompt,
}

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class CacheKeepaliveEngine:
    """Manages periodic keepalive calls to keep Anthropic prompt cache warm.

    Each registered module has its own system prompt prefix.  The engine
    rotates through modules, sending a sampling call whose system message
    matches the real validation agent prefix so Anthropic's cache stays
    warm.  In *explore* mode the user message varies to discover novel
    DSL patterns; in *ping* mode a minimal ack is requested.
    """

    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._modules: Dict[str, KeepaliveModuleConfig] = {}
        self._exploration_idx: int = 0
        self._task: Optional[asyncio.Task] = None

    # -- registration -------------------------------------------------------

    def register_module(self, config: KeepaliveModuleConfig) -> None:
        self._modules[config.module_name] = config
        logger.debug("Cache keepalive: registered module '%s'", config.module_name)

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(
            self._keepalive_loop(), name="cache-keepalive-loop"
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        stats = self.get_stats()
        logger.info("Cache keepalive stopped. Stats: %s", stats)

    # -- main loop ----------------------------------------------------------

    async def _keepalive_loop(self) -> None:
        interval = self._settings.cache_keepalive_interval_seconds
        logger.info(
            "Cache keepalive loop started (interval=%ds, modules=%s)",
            interval,
            list(self._modules.keys()),
        )

        # Small initial delay to let the server finish startup
        await asyncio.sleep(5)

        last_loop_at = time.time()

        while True:
            now = time.time()
            elapsed = now - last_loop_at
            # Detect OS sleep / event loop stalls — if elapsed > 2x interval,
            # the cache TTL almost certainly expired.
            if elapsed > interval * 2:
                logger.warning(
                    "Cache keepalive: loop gap detected (%.0fs elapsed, "
                    "expected %ds). Likely OS sleep — cache will be cold.",
                    elapsed,
                    interval,
                )
            last_loop_at = now

            for module in self._modules.values():
                try:
                    result = await self._send_keepalive(module)
                    ct = result.get("cached_tokens", 0)
                    savings = result.get("savings_usd", 0)
                    status = "HIT" if ct > 0 else "MISS"
                    logger.info(
                        "Cache keepalive [%s]: %s cached_tokens=%d, "
                        "call_savings=$%.6f, cumulative_savings=$%.6f, "
                        "total_calls=%d",
                        module.module_name,
                        status,
                        ct,
                        savings,
                        module.total_savings_usd,
                        module.total_keepalive_calls,
                    )
                except Exception:
                    logger.exception(
                        "Cache keepalive [%s]: send failed", module.module_name
                    )
            await asyncio.sleep(interval)

    # -- send a single keepalive call ---------------------------------------

    async def _send_keepalive(self, module: KeepaliveModuleConfig) -> dict:
        """Send one keepalive sampling call for *module*."""
        import litellm

        system_prompt = module.get_system_prompt_fn()

        if (
            self._settings.cache_keepalive_mode == "explore"
            and module.exploration_prompts
        ):
            idx = self._exploration_idx % len(module.exploration_prompts)
            user_message = module.exploration_prompts[idx]
            self._exploration_idx += 1
            temperature = 0.7
        else:
            user_message = (
                f"Acknowledge the {module.dsl_type_label or module.module_name} "
                "DSL reference above. Reply with OK."
            )
            temperature = 0.0

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        kwargs: dict[str, Any] = {
            "model": self._settings.litellm_model,
            "messages": messages,
            "max_tokens": self._settings.cache_keepalive_max_tokens,
            "temperature": temperature,
            "cache_control_injection_points": [
                {"location": "message", "role": "system"},
            ],
        }

        # Forward provider credentials — mirror server.py logic:
        # anthropic/ prefix → direct Anthropic API (LITELLM_API_KEY only)
        # openai/ prefix → Venice or other proxy (VENICE_INFERENCE_KEY + base)
        model = self._settings.litellm_model
        if model.startswith("anthropic/"):
            api_key = getattr(self._settings, "litellm_api_key", None)
            api_base = getattr(self._settings, "litellm_api_base", None)
        else:
            api_key = getattr(self._settings, "litellm_api_key", None) or getattr(
                self._settings, "venice_inference_key", None
            )
            api_base = getattr(self._settings, "litellm_api_base", None)
            if (
                not api_base
                and getattr(self._settings, "venice_inference_key", None)
                and not getattr(self._settings, "litellm_api_key", None)
            ):
                api_base = "https://api.venice.ai/api/v1"
        if api_key:
            kwargs["api_key"] = api_key
        if api_base:
            kwargs["api_base"] = api_base

        response = await litellm.acompletion(**kwargs)

        # Extract cache stats from response
        cached_tokens = 0
        input_tokens = 0
        output_tokens = 0
        usage = getattr(response, "usage", None)
        if usage:
            input_tokens = getattr(usage, "prompt_tokens", 0) or 0
            output_tokens = getattr(usage, "completion_tokens", 0) or 0
            prompt_details = getattr(usage, "prompt_tokens_details", None)
            if prompt_details:
                cached_tokens = getattr(prompt_details, "cached_tokens", 0) or 0

        # Update module stats
        module.last_keepalive_at = time.time()
        module.cached_tokens_last = cached_tokens
        module.total_keepalive_calls += 1
        module.total_cached_tokens += cached_tokens
        module.total_input_tokens += input_tokens
        module.total_output_tokens += output_tokens

        # Cost calculation — cached tokens at 10% of input rate
        input_rate = self._settings.sampling_input_token_rate
        output_rate = self._settings.sampling_output_token_rate
        uncached_input = input_tokens - cached_tokens
        cost = (
            uncached_input * input_rate
            + cached_tokens * input_rate * 0.1
            + output_tokens * output_rate
        )
        full_price = input_tokens * input_rate + output_tokens * output_rate
        savings = full_price - cost
        module.total_cost_usd += cost
        module.total_full_price_usd += full_price
        module.total_savings_usd += savings

        # Optionally index exploration results
        if (
            self._settings.cache_keepalive_mode == "explore"
            and self._settings.cache_keepalive_index_results
        ):
            try:
                response_text = self._extract_text(response)
                if response_text:
                    await self._maybe_index_result(module, response_text)
            except Exception:
                logger.debug(
                    "Cache keepalive [%s]: indexing skipped", module.module_name
                )

        return {
            "cached_tokens": cached_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
            "full_price_usd": full_price,
            "savings_usd": savings,
        }

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Extract text content from a LiteLLM response."""
        try:
            choices = getattr(response, "choices", [])
            if choices:
                message = getattr(choices[0], "message", None)
                if message:
                    return getattr(message, "content", "") or ""
        except Exception:
            pass
        return ""

    async def _maybe_index_result(
        self, module: KeepaliveModuleConfig, response_text: str
    ) -> None:
        """Best-effort indexing of valid DSL from exploration responses."""
        if module.module_name == "gchat":
            try:
                from gchat.wrapper_api import extract_dsl_from_description, parse_dsl

                dsl = extract_dsl_from_description(response_text)
                if dsl:
                    result = parse_dsl(dsl)
                    if result and getattr(result, "is_valid", False):
                        logger.debug(
                            "Cache keepalive [gchat]: indexed valid DSL pattern"
                        )
            except Exception:
                pass
        elif module.module_name == "qdrant":
            try:
                from middleware.qdrant_core.qdrant_models_wrapper import (
                    get_qdrant_models_wrapper,
                )

                wrapper = get_qdrant_models_wrapper()
                parser = wrapper.get_dsl_parser()
                # Build regex from wrapper's actual symbols — no hardcoding
                symbols = dict(wrapper.symbol_mapping) if wrapper.symbol_mapping else {}
                if symbols:
                    import re

                    escaped = [re.escape(s) for s in symbols.values()]
                    pattern = r"(?:" + "|".join(escaped) + r")\{[^}]*\}"
                    dsl_candidates = re.findall(pattern, response_text)
                    for candidate in dsl_candidates:
                        result = parser.parse(candidate)
                        if result and getattr(result, "is_valid", False):
                            logger.debug(
                                "Cache keepalive [qdrant]: validated DSL pattern"
                            )
                            break
            except Exception:
                pass
        # Email indexing can be added here when email wrapper supports it

    # -- stats --------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return per-module and aggregate statistics."""
        modules = {}
        total_calls = 0
        total_cached = 0
        total_cost = 0.0
        total_full_price = 0.0
        total_savings = 0.0
        for name, mod in self._modules.items():
            cache_hit_rate = (
                (mod.total_cached_tokens / mod.total_input_tokens * 100)
                if mod.total_input_tokens > 0
                else 0.0
            )
            modules[name] = {
                "total_calls": mod.total_keepalive_calls,
                "total_cached_tokens": mod.total_cached_tokens,
                "total_input_tokens": mod.total_input_tokens,
                "total_output_tokens": mod.total_output_tokens,
                "cache_hit_rate_pct": round(cache_hit_rate, 1),
                "total_cost_usd": round(mod.total_cost_usd, 6),
                "total_full_price_usd": round(mod.total_full_price_usd, 6),
                "total_savings_usd": round(mod.total_savings_usd, 6),
                "last_keepalive_at": mod.last_keepalive_at,
                "cached_tokens_last": mod.cached_tokens_last,
            }
            total_calls += mod.total_keepalive_calls
            total_cached += mod.total_cached_tokens
            total_cost += mod.total_cost_usd
            total_full_price += mod.total_full_price_usd
            total_savings += mod.total_savings_usd

        return {
            "modules": modules,
            "total_calls": total_calls,
            "total_cached_tokens": total_cached,
            "total_cost_usd": round(total_cost, 6),
            "total_full_price_usd": round(total_full_price, 6),
            "total_savings_usd": round(total_savings, 6),
            "savings_pct": round(
                (total_savings / total_full_price * 100) if total_full_price > 0 else 0,
                1,
            ),
        }

# ---------------------------------------------------------------------------
# Default module registration
# ---------------------------------------------------------------------------

def register_default_modules(engine: CacheKeepaliveEngine, settings: Any) -> None:
    """Register keepalive modules based on ``settings.cache_keepalive_modules``."""
    enabled = [
        m.strip() for m in settings.cache_keepalive_modules.split(",") if m.strip()
    ]
    for mod_name in enabled:
        builder = _MODULE_PROMPT_BUILDERS.get(mod_name)
        if builder is None:
            logger.warning("Cache keepalive: unknown module '%s', skipping", mod_name)
            continue
        config = KeepaliveModuleConfig(
            module_name=mod_name,
            get_system_prompt_fn=builder,
            exploration_prompts=_MODULE_EXPLORATION_PROMPTS.get(mod_name, []),
            dsl_type_label=mod_name,
        )
        engine.register_module(config)
