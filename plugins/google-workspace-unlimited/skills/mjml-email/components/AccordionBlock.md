# AccordionBlock

**Symbol:** `ą`

## Description

Expandable/collapsible accordion sections.

Renders via mj-accordion. Degrades gracefully in clients without
CSS support — all sections show expanded.

## Valid Children

- AccordionItem

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `background_color` | str? | No | — |  |
| `items` | list[AccordionItem] | Yes | — |  |
| `border` | str | No | `'1px solid #E2E8F0'` |  |
| `icon_position` | str | No | `'right'` |  |
| `padding` | str | No | `'0 0 12px 0'` |  |
| `font_family` | str? | No | — |  |
