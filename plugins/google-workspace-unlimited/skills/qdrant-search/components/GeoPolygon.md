# GeoPolygon

**Symbol:** `ǧ`

## Description

Geo filter request  Matches coordinates inside the polygon, defined by `exterior` and `interiors`

## Valid Children

- `G_1` GeoLineString

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `exterior` | GeoLineString | Yes | — | Geo filter request  Matches coordinates inside the polygon, defined by `exterior` and `interiors` |
| `interiors` | list[GeoLineString]? | No | — | Interior lines (if present) bound holes within the surface each GeoLineString must consist of a minimum of 4 points, and the first and last points must be the same. |
