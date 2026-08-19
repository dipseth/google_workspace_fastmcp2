# Jinja Template Filters

Google Chat cards support Jinja2 template expressions for dynamic content.

## Color Filters

Use these filters to style text with semantic colors:

| Filter | Color | Usage |
|--------|-------|-------|
| `success_text` | Green | `{{ 'Online' | success_text }}` |
| `error_text` | Red | `{{ 'Error' | error_text }}` |
| `warning_text` | Yellow | `{{ 'Warning' | warning_text }}` |
| `info_text` | Blue | `{{ 'Info' | info_text }}` |

## Custom Colors

Use the `color` filter with a hex value:

```jinja
{{ 'Custom text' | color('#FF5733') }}
```

## Text Styling

| Filter | Effect |
|--------|--------|
| `bold` | **Bold text** |
| `italic` | *Italic text* |
| `strike` | ~~Strikethrough~~ |

## Combining Filters

Filters can be chained:

```jinja
{{ 'Critical Error' | error_text | bold }}
```

## Examples

- `{{ 'Online' | success_text }} - Green text`
- `{{ 'Error' | error_text }} - Red text`
- `{{ 'Warning' | warning_text }} - Yellow text`
- `{{ text | color('#FF5733') }} - Custom orange text`
- `{{ 'Important' | bold }} - Bold text`


## Examples

- `{{ 'Online' | success_text }} - Green text`
- `{{ 'Error' | error_text }} - Red text`
- `{{ 'Warning' | warning_text }} - Yellow text`
- `{{ text | color('#FF5733') }} - Custom orange text`
- `{{ 'Important' | bold }} - Bold text`
