# PayloadIndexInfo

**Symbol:** `P_6`

## Description

Display payload field type &amp; index information

## Valid Children

- `P_7` PayloadSchemaType

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `data_type` | PayloadSchemaType | Yes | — | Display payload field type &amp; index information |
| `params` | Union[KeywordIndexParams, IntegerIndexParams, FloatIndexParams, GeoIndexParams, TextIndexParams, BoolIndexParams, DatetimeIndexParams, UuidIndexParams, NoneType] | No | — | Display payload field type &amp; index information |
| `points` | int | Yes | — | Number of points indexed with this index |
