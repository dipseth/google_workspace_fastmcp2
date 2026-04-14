# Bug: Validation Agent Structured Output Failure

## Symptom

```
middleware/sampling_middleware.py:1068 [E] ❌ LLM sampling failed for tool compose_dynamic_email:
Expected structured output of type ValidationResult, but the LLM returned a text response
instead of calling the final_response tool.

middleware/sampling_middleware.py:1305 [W] Validation agent failed for compose_dynamic_email:
LLM sampling failed: Expected structured output of type ValidationResult, but the LLM returned
a text response instead of calling the final_response tool.. Passing original input through.
```

## Impact

- The email still sends (graceful fallback: "Passing original input through")
- But the validation agent's corrections are lost — no pre-send validation occurs
- Affects `compose_dynamic_email` (and potentially other tools with pre-validation agents)

## Root Cause Investigation Needed

The validation agent is configured at `server.py:990-998`:

```python
sampling_middleware.register_validation_agent(
    "compose_dynamic_email",
    ValidationAgentConfig(
        tool_name="compose_dynamic_email",
        target_arg_keys=["email_description", "email_params"],
        get_system_prompt_fn=get_email_validation_prompt,
        mode="pre",
    ),
)
```

The sampling call at `middleware/sampling_middleware.py:1253-1271` uses `result_type=ValidationResult` which triggers structured output (tool-use with a `final_response` function). The LLM is returning plain text instead of calling the function.

## Key Files to Investigate

1. **`middleware/sampling_middleware.py`**
   - Line ~1068: Error is raised here
   - Line ~1253-1271: `sctx.sample()` call with `result_type=ValidationResult`
   - Line ~1281-1291: Response parsing into `ValidationResult`
   - The `SamplingContext.sample()` method (line ~916) — how it sets up structured output

2. **`middleware/litellm_sampling_handler.py`**
   - How `result_type` is translated to LiteLLM's `response_format` or `tools` parameter
   - Whether the tool-use format for structured output is correctly constructed

3. **`middleware/sampling_prompts/email_dsl.py`**
   - `get_email_validation_prompt()` — the system prompt sent to the validation LLM
   - May be too long/complex causing the LLM to ignore the tool-use instruction

4. **`server.py:969-1024`** — All validation agent registrations (4 total: card, email, macro, qdrant)

## Possible Causes

1. **System prompt too large** — The email validation prompt includes full DSL docs + symbols + validation checklist. If combined with the structured output tool definition, it may exceed the model's ability to follow both instructions.

2. **Model routing issue** — The LiteLLM model (`openai/claude-sonnet-4-6` via Venice proxy) may not fully support Anthropic-style tool-use for structured output through the proxy.

3. **Tool definition format** — The `final_response` tool definition for `ValidationResult` may not be correctly formatted for the provider being used.

4. **Temperature/token limits** — Validation agents use `temperature=0.1, max_tokens=400`. The structured response may need more tokens than allowed.

## Reproduction

Call `compose_dynamic_email` via the execute tool with any valid email params. Check server logs for the error. The email will still send but the validation agent error will appear.

## Suggested Fix Areas

- Check if the structured output (tool-use) format works with the configured LiteLLM provider
- Try increasing `max_tokens` for the email validation agent
- Consider simplifying the email validation prompt to reduce prompt size
- Test with `mode="parallel"` instead of `mode="pre"` to see if timing affects it
- Add a fallback in `SamplingContext.sample()` that extracts ValidationResult from plain text if structured output fails
