# Containment Rules for gmail.mjml_types

This document describes which components can contain which.

## Parent → Children Relationships

| Parent | Symbol | Children |
|--------|--------|----------|
| AccordionBlock | `ą` | `A`=AccordionItem |
| CarouselBlock | `ȼ` | `C`=CarouselImage |
| Column | `©` | `E`=EmailBlock |
| ColumnsBlock | `¢` | `©`=Column |
| EmailSpec | `ε` | `E`=EmailTheme |
| MjmlRenderResult | `-` | `M`=MjmlDiagnostic |
| SocialBlock | `ʂ` | `S`=SocialLink |
| TableBlock | `ƭ` | `T`=TableRow |