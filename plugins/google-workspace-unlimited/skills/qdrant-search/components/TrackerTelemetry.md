# TrackerTelemetry

**Symbol:** `T_0`

## Description

Tracker object used in telemetry

## Valid Children

- `ü` UUID

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | str | Yes | — | Name of the optimizer |
| `uuid` | UUID | Yes | — | UUID of the upcoming segment being created by the optimizer |
| `segment_ids` | list[int] | Yes | — | Internal segment IDs being optimized. These are local and in-memory, meaning that they can refer to different segments after a service restart. |
| `segment_uuids` | list[UUID] | Yes | — | Segment UUIDs being optimized. Refers to same segments as in `segment_ids`, but trackable across restarts, and reflect their directory name. |
| `status` | Union[TrackerStatusOneOf, TrackerStatusOneOf1, TrackerStatusOneOf2] | Yes | — | Tracker object used in telemetry |
| `start_at` | Union[datetime, date] | Yes | — | Start time of the optimizer |
| `end_at` | Union[datetime, date, NoneType] | No | — | End time of the optimizer |
