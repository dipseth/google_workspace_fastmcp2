# FieldCondition

**Symbol:** `ʄ`

## Description

All possible payload filtering conditions

## Valid Children

- `G_3` GeoBoundingBox
- `ǧ` GeoPolygon
- `ǵ` GeoRadius
- `ν` ValuesCount

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `key` | str | Yes | — | Payload key |
| `match` | Union[MatchValue, MatchText, MatchTextAny, MatchPhrase, MatchAny, MatchExcept, NoneType] | No | — | Check if point has field with a given value |
| `range` | Union[Range, DatetimeRange, NoneType] | No | — | Check if points value lies in a given range |
| `geo_bounding_box` | GeoBoundingBox? | No | — | Check if points geolocation lies in a given area |
| `geo_radius` | GeoRadius? | No | — | Check if geo point is within a given radius |
| `geo_polygon` | GeoPolygon? | No | — | Check if geo point is within a given polygon |
| `values_count` | ValuesCount? | No | — | Check number of values of the field |
| `is_empty` | bool? | No | — | Check that the field is empty, alternative syntax for `is_empty: 'field_name'` |
| `is_null` | bool? | No | — | Check that the field is null, alternative syntax for `is_null: 'field_name'` |
