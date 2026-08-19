# Card Params Reference

How to structure `card_params` when using DSL notation with `send_dynamic_card`.

## Structure DSL vs Content DSL

- `card_description`: Accepts **both** Structure DSL (`§[δx2]`) and Content DSL (`δ 'text' success bold`)
- `card_params`: Explicit content overrides keyed by symbol — always takes priority over Content DSL

## Symbol-Keyed Params

Use DSL symbols as keys in `card_params` for direct correspondence with the DSL structure.

### Symbol to Flat Key Mapping

| Symbol | Component | Flat Key | Purpose |
|--------|-----------|----------|---------|
| `δ` | DecoratedText | `items` | List of decorated text widgets |
| `ʈ` | TextParagraph | `items` | List of text paragraph widgets |
| `ᵬ` | Button | `buttons` | List of button widgets |
| `ǵ` | GridItem | `grid_items` | List of grid cells |
| `▼` | CarouselCard | `cards` | List of carousel card widgets |
| `ℂ` | Chip | `chips` | List of chip widgets |

Container symbols (`§`, `Ƀ`, `ℊ`, `◦`, `¢`, `ȼ`) have no param key — use their children's symbols.

## Three Formats

### Format A: Direct List
```json
{"δ": [{"text": "Item 1", "top_label": "Status"}, {"text": "Item 2"}]}
```

### Format B: _shared/_items (DRY — recommended)
```json
{
  "δ": {
    "_shared": {"top_label": "Status", "icon": "check_circle"},
    "_items": [
      {"text": "Drive: Online"},
      {"text": "Gmail: Online"}
    ]
  }
}
```
Each `_items` entry is merged with `_shared` (item fields override shared).

### Format C: Single Dict (auto-wrapped in list)
```json
{"ᵬ": {"text": "Click Me", "url": "https://example.com"}}
```

## Component Field Reference

### DecoratedText (`δ`)
- `text` (**required**) — Main content (supports HTML: `<b>`, `<font color="...">`)
- `top_label` — Small label above text
- `bottom_label` — Small label below text
- `icon` — Google Material icon name (e.g., `star`, `check_circle`, `error`)

### Button (`ᵬ`)
- `text` (**required**) — Button label
- `url` — Click target URL
- `icon` — Optional icon name

### GridItem (`ǵ`)
- `title` (**required**) — Item title
- `subtitle` — Optional subtitle
- `image_url` — Optional image URL

### CarouselCard (`▼`)
- `title` (**required**) — Card title
- `subtitle` — Optional subtitle
- `text` — Optional card body
- `image_url` — Optional image
- `buttons` — Optional list of `{text, url}` dicts

### TextParagraph (`ʈ`)
- `text` (**required**) — Paragraph text (supports HTML)

## Important Rules

1. **Item count must match DSL multiplier**: `δ×3` requires exactly 3 items in `_items`
2. **Symbol keys override flat keys**: If both `δ` and `items` exist, `δ` wins
3. **Backward compatible**: Flat keys (`items`, `buttons`, `grid_items`) still work
4. **`title` and `subtitle`** are card-level params, not symbol-keyed

## Full Example

DSL: `§[δ×2, Đ, Ƀ[ᵬ×2]]`

```json
{
  "title": "System Status",
  "subtitle": "All services",
  "δ": {
    "_shared": {"icon": "monitoring", "top_label": "Service"},
    "_items": [
      {"text": "API: <font color=\"#34a853\"><b>Online</b></font>"},
      {"text": "DB: <font color=\"#fbbc04\"><b>Warning</b></font>"}
    ]
  },
  "ᵬ": [
    {"text": "View Details", "url": "https://example.com/details"},
    {"text": "Export CSV", "url": "https://example.com/export"}
  ]
}
```
