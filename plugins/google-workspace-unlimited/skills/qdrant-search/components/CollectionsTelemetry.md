# CollectionsTelemetry

**Symbol:** `C_20`

## Description

Fields: number_of_collections (int); max_collections (int); collections (list[CollectionTelemetry | CollectionsAggregatedTelemetry]); snapshots (list[CollectionSnapshotTelemetry]).

## Valid Children

- `C_29` CollectionSnapshotTelemetry

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `number_of_collections` | int | Yes | — |  |
| `max_collections` | int? | No | — |  |
| `collections` | list[Union[CollectionTelemetry, CollectionsAggregatedTelemetry]]? | No | — |  |
| `snapshots` | list[CollectionSnapshotTelemetry]? | No | — |  |
