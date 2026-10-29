# TelemetryData

**Symbol:** `ŧ`

## Description

Fields: id (str); app (AppBuildTelemetry); collections (CollectionsTelemetry); cluster (ClusterTelemetry); requests (RequestsTelemetry); memory (MemoryTelemetry); hardware (HardwareTelemetry).

## Valid Children

- `ă` AppBuildTelemetry
- `C_3` ClusterTelemetry
- `C_20` CollectionsTelemetry
- `H_0` HardwareTelemetry
- `M_2` MemoryTelemetry
- `R_9` RequestsTelemetry

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | str | Yes | — |  |
| `app` | AppBuildTelemetry? | No | — |  |
| `collections` | CollectionsTelemetry | Yes | — |  |
| `cluster` | ClusterTelemetry? | No | — |  |
| `requests` | RequestsTelemetry? | No | — |  |
| `memory` | MemoryTelemetry? | No | — |  |
| `hardware` | HardwareTelemetry? | No | — |  |
