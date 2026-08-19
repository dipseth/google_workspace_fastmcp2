# Email Params Reference

How to structure `email_params` when using DSL notation with `compose_dynamic_email`.

## Critical: Structure vs Content Separation

- `email_description` = **structure ONLY** (DSL symbols + optional subject after the DSL)
- `email_params` = **ALL content** (titles, text, URLs, keyed by symbol)

WRONG: `email_description: "ε[ħ 'My Title', τ 'Body text']"`
RIGHT: `email_description: "ε[ħ, τ] My Subject"` + `email_params: {"ħ": {"title": "My Title"}, "τ": {"text": "Body text"}}`

## Symbol-Keyed Params

Use DSL symbols as keys in `email_params`. Symbols resolve to block class names.

### Symbol to Block Mapping

| Symbol | Block | Purpose |
|--------|-------|---------|
| `ħ` | HeroBlock | Hero banner with title, subtitle, CTA |
| `τ` | TextBlock | Rich text content block |
| `Ƀ` | ButtonBlock | Call-to-action button |
| `ɨ` | ImageBlock | Responsive image |
| `Ħ` | HeaderBlock | Email header/logo |
| `ƒ` | FooterBlock | Email footer with links |
| `ş` | SpacerBlock | Vertical spacing |
| `đ` | DividerBlock | Horizontal rule divider |
| `¢` | ColumnsBlock | Multi-column layout container |
| `ʂ` | SocialBlock | Social media links |
| `ƭ` | TableBlock | Data table |
| `ą` | AccordionBlock | Expandable accordion sections |

## Three Formats

### Format A: Direct Dict
```json
{"ħ": {"title": "Welcome!", "subtitle": "Hello there"}}
```

### Format B: _shared/_items (DRY — for repeated blocks)
```json
{
  "τ": {
    "_shared": {"font_size": "14px"},
    "_items": [
      {"text": "First paragraph..."},
      {"text": "Second paragraph..."}
    ]
  }
}
```
Each `_items` entry is merged with `_shared` (item fields override shared).

### Format C: Single Dict (consumed once per block instance)
```json
{"Ƀ": {"text": "Get Started", "url": "https://example.com"}}
```

## Block Field Reference

### HeroBlock (`ħ`)
- `title` (**required**) — Main heading
- `subtitle` — Subheading text
- `cta_text` — Call-to-action button text
- `cta_url` — CTA button URL
- `background_image_url` — Hero background image
- `title_color`, `subtitle_color` — Hex colors

### TextBlock (`τ`)
- `text` (**required**) — Rich text content (supports HTML)
- `font_size` — Default: `16px`
- `color` — Text color (hex)
- `align` — `left`, `center`, `right`

### ButtonBlock (`Ƀ`)
- `text` (**required**) — Button label
- `url` (**required**) — Click target URL
- `background_color` — Button background (hex)
- `color` — Text color (default: `#ffffff`)
- `border_radius` — Default: `8px`
- `align` — `left`, `center`, `right`

### ImageBlock (`ɨ`)
- `src` (**required**) — Image URL
- `alt` — Alt text
- `width` — Image width (e.g., `600px`)
- `href` — Optional link URL

### HeaderBlock (`Ħ`)
- `logo_url` — Logo image URL
- `logo_alt` — Logo alt text
- `title` — Header title text

### FooterBlock (`ƒ`)
- `text` (**required**) — Footer content (HTML supported)
- `links` — List of `{text, url}` dicts

## Important Rules

1. **Item count must match DSL multiplier**: `τ×3` requires 3 items in `_items`
2. **Symbol keys resolve to class names**: `ħ` resolves to `HeroBlock`
3. **`subject` and `preheader`** are top-level email_params keys (not symbol-keyed)
4. **DSL goes in `email_description`**, content goes in `email_params`

## Full Example

email_description: `ε[ħ, τ×2, Ƀ] Welcome to Acme`

email_params:
```json
{
  "subject": "Welcome to Acme",
  "preheader": "Your account is ready",
  "ħ": {"title": "Welcome!", "subtitle": "Your account is ready", "cta_text": "Get Started", "cta_url": "https://example.com/start"}},
  "τ": {
    "_items": [
      {"text": "Thanks for signing up..."},
      {"text": "Here is what you can do next..."}
    ]
  },
  "Ƀ": {"text": "Open Dashboard", "url": "https://example.com/dashboard"}
}
```
