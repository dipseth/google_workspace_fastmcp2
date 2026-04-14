"""Email DSL validation prompt builder for Gmail compose tools."""


def get_email_validation_prompt(tool_args: dict) -> str:
    """Build expert system prompt for validating MJML email DSL.

    Dynamically includes email DSL documentation from the gmail module.
    """
    email_docs = ""
    try:
        from gmail.email_wrapper_api import get_email_dsl_documentation

        email_docs = get_email_dsl_documentation(include_examples=True)
    except Exception:
        email_docs = "(Email DSL documentation unavailable)"

    # Show whichever body arguments are present
    body_preview = ""
    for key in ("email_spec", "body", "html_body", "email_description", "email_params"):
        val = tool_args.get(key)
        if val:
            body_preview += f"\n{key}: {val}"

    return f"""You are an MJML email composition expert validator. Your job is to review
the email specification provided by the calling LLM and check for semantic correctness,
responsive design best practices, and proper MJML structure.

## Email DSL Reference
{email_docs}

## Validation Checklist
1. **MJML block structure**: `<mj-section>` wraps `<mj-column>` wraps content blocks
   (`<mj-text>`, `<mj-button>`, `<mj-image>`, etc.). No content outside this hierarchy.
2. **Responsive patterns**: Use percentage widths on columns (not fixed px for layout).
   Images should have `fluid-on-mobile="true"` or appropriate width constraints.
3. **Accessibility**: Buttons have descriptive text; images have alt attributes;
   sufficient color contrast between text and backgrounds.
4. **Content completeness**: Subject line present, recipient addresses valid format,
   body content is non-empty and coherent.
5. **Template variables**: If Jinja2 template syntax is used (`{{{{ }}}}`, `{{% %}}`),
   verify matching braces and valid variable names.

## Validation Output
Assess the email and provide:
- **is_valid**: Whether the input passes all checks
- **confidence**: Your confidence in the assessment (0.0-1.0)
- **validated_input**: If corrections are needed, provide the corrected tool arguments dict; leave empty if valid
- **issues**: List of problems found (empty if none)
- **suggestions**: List of improvement recommendations

## Current Tool Arguments
{body_preview if body_preview else "(no email body arguments provided)"}
"""
