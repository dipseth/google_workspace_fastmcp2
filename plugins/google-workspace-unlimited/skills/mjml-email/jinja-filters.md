# Email Jinja Template Filters

MJML email templates support Jinja2 expressions for dynamic content within `email_params`.

## Color Filters

| Filter | Color | Usage |
|--------|-------|-------|
| `success_text` | Green | `{{ 'Active' | success_text }}` |
| `error_text` | Red | `{{ 'Overdue' | error_text }}` |
| `warning_text` | Yellow | `{{ 'Pending' | warning_text }}` |
| `info_text` | Blue | `{{ 'New' | info_text }}` |

## Text Styling

| Filter | Effect |
|--------|--------|
| `bold` | **Bold text** |
| `italic` | *Italic text* |
| `strike` | ~~Strikethrough~~ |

## Combining Filters

```jinja
{{ 'Critical Alert' | error_text | bold }}
```

## Dual-Mode Macros

Email macros support two modes:
- **DSL mode**: Returns structure notation (e.g., `EmailSpec[HeroBlock, TextBlock×3, FooterBlock]`)
- **Params mode**: Returns JSON `email_params` with symbol keys

```
email_description: {{ email_workspace_digest(service://gmail/labels, email_symbols, 'dsl') }}
email_params:      {{ email_workspace_digest(service://gmail/labels, email_symbols, 'params') }}
```

## Examples

- `{{ 'Active' | success_text }} — Green text`
- `{{ 'Overdue' | error_text }} — Red text`
- `{{ count ~ ' unread' | bold }} — Bold count`
- `{{ label.name | info_text }} — Blue label name`


## Examples

- `{{ 'Active' | success_text }} — Green text`
- `{{ 'Overdue' | error_text }} — Red text`
- `{{ count ~ ' unread' | bold }} — Bold count`
- `{{ label.name | info_text }} — Blue label name`
