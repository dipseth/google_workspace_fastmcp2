# GeoBoundingBox

**Symbol:** `G_3`

## Description

Geo filter request  Matches coordinates inside the rectangle, described by coordinates of lop-left and bottom-right edges

## Valid Children

- `ℊ` GeoPoint
- `ℊ` GeoPoint
- `ℊ` GeoPoint
- `ℊ` GeoPoint

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `top_left` | GeoPoint | Yes | — | Geo filter request  Matches coordinates inside the rectangle, described by coordinates of lop-left and bottom-right edges |
| `bottom_right` | GeoPoint | Yes | — | Geo filter request  Matches coordinates inside the rectangle, described by coordinates of lop-left and bottom-right edges |
