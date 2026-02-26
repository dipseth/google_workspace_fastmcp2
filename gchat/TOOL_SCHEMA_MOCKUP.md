# send_dynamic_card Tool Schema

This is how the `send_dynamic_card` tool appears to LLMs via MCP.

## Tool Description

> Send cards to Google Chat using DSL notation for precise structure control. REQUIRED: Use DSL symbols in card_description to define card structure. Common patterns: §[δ] = text card, §[δ, Ƀ[ᵬ×2]] = text + 2 buttons, §[ℊ[ǵ×4]] = grid with 4 items. DSL structure using symbols. Examples: '§[δ, Ƀ[ᵬ×2]]' = Section + text + 2 buttons, '◦[▲×3]' = Carousel with 3 cards. Symbols: §=Section, δ=DecoratedText, Ƀ=ButtonList, ᵬ=Button, ℊ=Grid, ǵ=GridItem, ◦=Carousel, ▲=CarouselCard, ŋ=NestedWidget. Read skill://gchat-cards/ for full reference.

**Length:** 535 chars

---

## Input Schema

### Required Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `user_google_email` | string | Google email for authentication |
| `card_description` | string | DSL structure defining the card layout |

### Optional Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `space_id` | string | Chat space ID (optional when using webhook) |
| `card_params` | object | Content: title, subtitle, text, buttons, images |
| `webhook_url` | string | Webhook URL (defaults to env var) |
| `thread_key` | string | Thread key for replies |

### card_description Field Help

> IMPORTANT: Start with DSL symbols to define card structure. Without DSL, cards render as simple text only. DSL Examples: §[δ] = Section with DecoratedText, §[δ, Ƀ[ᵬ×2]] = text + 2 buttons, §[δ×3] = 3 text items, §[ℊ[ǵ×4]] = grid with 4 items. Provide content in card_params: title, subtitle, text, buttons=[{text, url}]. Jinja styling in text: {{ 'Online' | success_text }}, {{ text | color('#hex') }}. DSL structure using symbols. Examples: '§[δ, Ƀ[ᵬ×2]]' = Section + text + 2 buttons, '◦[▲×3]' = Carousel with 3 cards. Symbols: §=Section, δ=DecoratedText, Ƀ=ButtonList, ᵬ=Button, ℊ=Grid, ǵ=GridItem, ◦=Carousel, ▲=CarouselCard, ŋ=NestedWidget. Read skill://gchat-cards/ for full reference.

**Length:** 691 chars

---

## Annotations

### dsl_documentation

```markdown
## Card DSL Quick Reference

### Core Symbols
**Card:** ©=Card, ◇=CardHeader, §=Section
**Carousel:** ◦=Carousel, ▲=CarouselCard, ŋ=NestedWidget
**Containers:** Ƀ=ButtonList, ȼ=ChipList, ℊ=Grid, ¢=Columns
**Widgets:** δ=DecoratedText, ʈ=TextParagraph, ǐ=Image, Đ=Divider
**Items:** ᵬ=Button, ℂ=Chip, ǵ=GridItem, ç=Column

### Containment Rules
- § Section → δ ʈ ǐ Ƀ ȼ ℊ ¢
- ◦ Carousel → ▲ CarouselCard → ŋ NestedWidget → ʈ Ƀ ǐ
- Ƀ ButtonList → ᵬ, ȼ ChipList → ℂ
- ℊ Grid → ǵ, ¢ Columns → ç

### Examples
- `§[δ]` → Section with text
- `§[δ, Ƀ[ᵬ×2]]` → Text + 2 buttons
- `§[ℊ[ǵ×4]]` → Grid with 4 items
- `◦[▲×3]` → Carousel with 3 cards
- Syntax: `×N` = multiplier, `[]` = children, `,` = siblings

### More Info
Read `skill://gchat-cards/` resources for complete docs (100+ components).
```

**Length:** 788 chars

### Examples

```json
[
  {
    "description": "Basic text card",
    "card_description": "\u00a7[\u03b4]",
    "card_params": {
      "title": "Alert",
      "text": "System update complete"
    }
  },
  {
    "description": "Text + 2 buttons",
    "card_description": "\u00a7[\u03b4, \u0243[\u1d6c\u00d72]]",
    "card_params": {
      "title": "Actions",
      "text": "Choose an action",
      "buttons": [
        {
          "text": "Approve",
          "url": "https://example.com/yes"
        },
        {
          "text": "Reject",
          "url": "https://example.com/no"
        }
      ]
    }
  },
  {
    "description": "Grid with 4 items",
    "card_description": "\u00a7[\u210a[\u01f5\u00d74]]",
    "card_params": {
      "title": "Gallery",
      "grid_items": [
        {
          "title": "Item 1"
        },
        {
          "title": "Item 2"
        },
        {
          "title": "Item 3"
        },
        {
          "title": "Item 4"
        }
      ]
    }
  },
  {
    "description": "Carousel with 3 cards",
    "card_description": "\u25e6[\u25b2\u00d73]",
    "card_params": {
      "title": "Slideshow",
      "carousel_items": [
        {
          "text": "Slide 1"
        },
        {
          "text": "Slide 2"
        },
        {
          "text": "Slide 3"
        }
      ]
    }
  }
]
```

---

## Complete JSON Schema

```json
{
  "name": "send_dynamic_card",
  "title": "Send Dynamic Card with NLP",
  "description": "Send cards to Google Chat using DSL notation for precise structure control. REQUIRED: Use DSL symbols in card_description to define card structure. Common patterns: \u00a7[\u03b4] = text card, \u00a7[\u03b4, \u0243[\u1d6c\u00d72]] = text + 2 buttons, \u00a7[\u210a[\u01f5\u00d74]] = grid with 4 items. DSL structure using symbols. Examples: '\u00a7[\u03b4, \u0243[\u1d6c\u00d72]]' = Section + text + 2 buttons, '\u25e6[\u25b2\u00d73]' = Carousel with 3 cards. Symbols: \u00a7=Section, \u03b4=DecoratedText, \u0243=ButtonList, \u1d6c=Button, \u210a=Grid, \u01f5=GridItem, \u25e6=Carousel, \u25b2=CarouselCard, \u014b=NestedWidget. Read skill://gchat-cards/ for full reference.",
  "inputSchema": {
    "properties": {
      "user_google_email": {
        "description": "Google email for authentication",
        "type": "string"
      },
      "card_description": {
        "description": "IMPORTANT: Start with DSL symbols to define card structure. Without DSL, cards render as simple text only. DSL Examples: \u00a7[\u03b4] = Section with DecoratedText, \u00a7[\u03b4, \u0243[\u1d6c\u00d72]] = text + 2 buttons, \u00a7[\u03b4\u00d73] = 3 text items, \u00a7[\u210a[\u01f5\u00d74]] = grid with 4 items. Provide content in card_params: title, subtitle, text, buttons=[{text, url}]. Jinja styling in text: {{ 'Online' | success_text }}, {{ text | color('#hex') }}. DSL structure using symbols. Examples: '\u00a7[\u03b4, \u0243[\u1d6c\u00d72]]' = Section + text + 2 buttons, '\u25e6[\u25b2\u00d73]' = Carousel with 3 cards. Symbols: \u00a7=Section, \u03b4=DecoratedText, \u0243=ButtonList, \u1d6c=Button, \u210a=Grid, \u01f5=GridItem, \u25e6=Carousel, \u25b2=CarouselCard, \u014b=NestedWidget. Read skill://gchat-cards/ for full reference.",
        "type": "string"
      },
      "space_id": {
        "description": "Chat space ID (e.g., 'spaces/AAAA1234'). Optional when using webhook.",
        "type": "string",
        "default": null
      },
      "card_params": {
        "description": "Explicit overrides: title, subtitle, text, buttons, images. Supports Jinja filters.",
        "type": "object",
        "default": null
      },
      "webhook_url": {
        "description": "Webhook URL. Defaults to MCP_CHAT_WEBHOOK env var.",
        "type": "string",
        "default": null
      },
      "thread_key": {
        "description": "Thread key for replies",
        "type": "string",
        "default": null
      }
    },
    "required": [
      "user_google_email",
      "card_description"
    ],
    "type": "object"
  },
  "annotations": {
    "title": "Send Dynamic Card with NLP",
    "readOnlyHint": false,
    "destructiveHint": false,
    "idempotentHint": false,
    "openWorldHint": true,
    "dsl_documentation": "## Card DSL Quick Reference\n\n### Core Symbols\n**Card:** \u00a9=Card, \u25c7=CardHeader, \u00a7=Section\n**Carousel:** \u25e6=Carousel, \u25b2=CarouselCard, \u014b=NestedWidget\n**Containers:** \u0243=ButtonList, \u023c=ChipList, \u210a=Grid, \u00a2=Columns\n**Widgets:** \u03b4=DecoratedText, \u0288=TextParagraph, \u01d0=Image, \u0110=Divider\n**Items:** \u1d6c=Button, \u2102=Chip, \u01f5=GridItem, \u00e7=Column\n\n### Containment Rules\n- \u00a7 Section \u2192 \u03b4 \u0288 \u01d0 \u0243 \u023c \u210a \u00a2\n- \u25e6 Carousel \u2192 \u25b2 CarouselCard \u2192 \u014b NestedWidget \u2192 \u0288 \u0243 \u01d0\n- \u0243 ButtonList \u2192 \u1d6c, \u023c ChipList \u2192 \u2102\n- \u210a Grid \u2192 \u01f5, \u00a2 Columns \u2192 \u00e7\n\n### Examples\n- `\u00a7[\u03b4]` \u2192 Section with text\n- `\u00a7[\u03b4, \u0243[\u1d6c\u00d72]]` \u2192 Text + 2 buttons\n- `\u00a7[\u210a[\u01f5\u00d74]]` \u2192 Grid with 4 items\n- `\u25e6[\u25b2\u00d73]` \u2192 Carousel with 3 cards\n- Syntax: `\u00d7N` = multiplier, `[]` = children, `,` = siblings\n\n### More Info\nRead `skill://gchat-cards/` resources for complete docs (100+ components).",
    "examples": [
      {
        "description": "Basic text card",
        "card_description": "\u00a7[\u03b4]",
        "card_params": {
          "title": "Alert",
          "text": "System update complete"
        }
      },
      {
        "description": "Text + 2 buttons",
        "card_description": "\u00a7[\u03b4, \u0243[\u1d6c\u00d72]]",
        "card_params": {
          "title": "Actions",
          "text": "Choose an action",
          "buttons": [
            {
              "text": "Approve",
              "url": "https://example.com/yes"
            },
            {
              "text": "Reject",
              "url": "https://example.com/no"
            }
          ]
        }
      },
      {
        "description": "Grid with 4 items",
        "card_description": "\u00a7[\u210a[\u01f5\u00d74]]",
        "card_params": {
          "title": "Gallery",
          "grid_items": [
            {
              "title": "Item 1"
            },
            {
              "title": "Item 2"
            },
            {
              "title": "Item 3"
            },
            {
              "title": "Item 4"
            }
          ]
        }
      },
      {
        "description": "Carousel with 3 cards",
        "card_description": "\u25e6[\u25b2\u00d73]",
        "card_params": {
          "title": "Slideshow",
          "carousel_items": [
            {
              "text": "Slide 1"
            },
            {
              "text": "Slide 2"
            },
            {
              "text": "Slide 3"
            }
          ]
        }
      }
    ]
  }
}
```

---

## Size Summary

| Component | Characters |
|-----------|------------|
| Tool description | 535 |
| card_description help | 691 |
| dsl_documentation | 788 |
| **Total key text** | **2014** |

*Previously this was ~15,000+ characters with all 109 components listed.*
