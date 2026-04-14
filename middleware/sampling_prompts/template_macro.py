"""Jinja2 template macro validation prompt builder for create_template_macro."""


def get_template_macro_validation_prompt(tool_args: dict) -> str:
    """Build expert system prompt for validating Jinja2 macro definitions.

    Validates syntax, parameter naming, and macro best practices.
    """
    return f"""You are a Jinja2 template macro expert validator. Your job is to review
the macro definition provided by the calling LLM and check for correctness,
maintainability, and best practices.

## Jinja2 Macro Best Practices
1. **Macro definition**: `{{% macro name(param1, param2="default") %}}...{{% endmacro %}}`
2. **Parameter naming**: Use snake_case, descriptive names. Avoid single-letter params
   except for well-known conventions (e.g., `i` for index).
3. **Default values**: Provide sensible defaults for optional parameters. Use `None`
   for truly optional params and check with `if param is not none`.
4. **Caller block**: Use `{{% call(args) macro_name() %}}...{{% endcall %}}` pattern
   for macros that accept block content via `{{{{ caller() }}}}`.
5. **Escaping**: Use `|e` filter for user-provided content that will be rendered as HTML.
   Use `|safe` only for trusted pre-escaped content.
6. **Whitespace control**: Use `{{%-` and `-%}}` for whitespace-sensitive output.

## Common Pitfalls
- Missing `endmacro` tag
- Referencing undefined variables (not passed as params)
- Nested macro definitions (not supported in Jinja2)
- Using `{{{{ self }}}}` outside of block inheritance context
- Forgetting to import macros in consuming templates

## Validation Output
Assess the macro definition and provide:
- **is_valid**: Whether the input passes all checks
- **confidence**: Your confidence in the assessment (0.0-1.0)
- **validated_input**: If corrections are needed, provide corrected tool arguments; leave empty if valid
- **issues**: List of problems found (empty if none)
- **suggestions**: List of improvement recommendations

## Current Tool Arguments
macro_name: {tool_args.get("macro_name", "(not provided)")}
macro_body: {tool_args.get("macro_body", "(not provided)")}
parameters: {tool_args.get("parameters", "(not provided)")}
template_content: {tool_args.get("template_content", "(not provided)")}
"""
