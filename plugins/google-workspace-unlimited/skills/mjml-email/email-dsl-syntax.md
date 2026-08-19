# Email DSL Syntax

MJML emails use a compact DSL notation for defining block structure.

## Basic Syntax

```
ε[ħ, τ×2, Ƀ]
```

Means: EmailSpec with HeroBlock, 2 TextBlocks, and a ButtonBlock.

## Notation Rules

- **Symbols**: Each block type has a unique Unicode symbol (see `symbols.md`)
- **Brackets**: `[]` denote children of a container
- **Multiplier**: `×N` creates N copies of a block
- **Comma**: Separates sibling blocks

## Symbol Table

**A:** ą=AccordionBlock
**B:** Ƀ=ButtonBlock
**C:** ȼ=CarouselBlock, ©=Column, ¢=ColumnsBlock
**D:** đ=DividerBlock
**E:** ε=EmailSpec
**F:** ƒ=FooterBlock
**H:** Ħ=HeaderBlock, ħ=HeroBlock
**I:** ɨ=ImageBlock
**S:** ʂ=SocialBlock, ş=SpacerBlock
**T:** ƭ=TableBlock, τ=TextBlock

## Containment Rules

- EmailSpec → all block types (top-level container)
- ColumnsBlock → Column (layout container)
- Column → TextBlock, ButtonBlock, ImageBlock, SpacerBlock, DividerBlock

## Examples

- `ε[ħ, τ] — EmailSpec with HeroBlock and TextBlock`
- `ε[Ħ, ħ, τ×3, Ƀ] — Header, hero, 3 text blocks, button`
- `ε[ħ, ¢[©×2], Ƀ] — Hero, 2-column layout, button`
- `ε[Ħ, τ, đ, ƒ] — Header, text, divider, footer`
