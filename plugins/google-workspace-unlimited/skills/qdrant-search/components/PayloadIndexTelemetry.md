# PayloadIndexTelemetry

**Symbol:** `P_13`

## Description

Fields: field_name (str); index_type (str); points_values_count (int): The amount of values indexed for all points.; points_count (int): The amount of points that have at least one value indexed.; histogram_bucket_size (int).

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `field_name` | str? | No | — |  |
| `index_type` | str | Yes | — |  |
| `points_values_count` | int | Yes | — | The amount of values indexed for all points. |
| `points_count` | int | Yes | — | The amount of points that have at least one value indexed. |
| `histogram_bucket_size` | int? | No | — |  |
