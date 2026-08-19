# CarouselBlock

**Symbol:** `ȼ`

## Description

Image carousel with navigation arrows and thumbnails.

Renders via mj-carousel. Best support in Apple Mail and iOS;
falls back to first image in Gmail/Outlook.

## Valid Children

- CarouselImage

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `background_color` | str? | No | — |  |
| `images` | list[CarouselImage] | Yes | — |  |
| `thumbnails` | str | No | `'visible'` |  |
| `border_radius` | str | No | `'6px'` |  |
| `icon_width` | str | No | `'44px'` |  |
| `padding` | str | No | `'0 0 12px 0'` |  |
