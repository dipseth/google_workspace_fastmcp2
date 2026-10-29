# CreateFieldIndex

**Symbol:** `C_7`

## Description

Fields: field_name (str); field_schema (PayloadSchemaType | KeywordIndexParams | IntegerIndexParams | FloatIndexParams | GeoIndexParams | TextIndexParams | BoolIndexParams | DatetimeIndexParams | UuidIndexParams).

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `field_name` | str | Yes | — |  |
| `field_schema` | Union[PayloadSchemaType, KeywordIndexParams, IntegerIndexParams, FloatIndexParams, GeoIndexParams, TextIndexParams, BoolIndexParams, DatetimeIndexParams, UuidIndexParams, NoneType] | No | — |  |
