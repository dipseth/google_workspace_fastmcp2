# GeoRadius

**Symbol:** `ǵ`

## Description

Geo filter request  Matches coordinates inside the circle of `radius` and center with coordinates `center`

## Valid Children

- `ℊ` GeoPoint
- `ℊ` GeoPoint

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `center` | GeoPoint | Yes | — | Geo filter request  Matches coordinates inside the circle of `radius` and center with coordinates `center` |
| `radius` | float | Yes | — | Radius of the area in meters |
