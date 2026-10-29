# SegmentTelemetry

**Symbol:** `S_6`

## Description

Fields: info (SegmentInfo); config (SegmentConfig); vector_index_searches (list[VectorIndexSearchesTelemetry]); payload_field_indices (list[PayloadIndexTelemetry]).

## Valid Children

- `P_13` PayloadIndexTelemetry
- `S_4` SegmentConfig
- `σ` SegmentInfo
- `V_1` VectorIndexSearchesTelemetry

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `info` | SegmentInfo | Yes | — |  |
| `config` | SegmentConfig | Yes | — |  |
| `vector_index_searches` | list[VectorIndexSearchesTelemetry] | Yes | — |  |
| `payload_field_indices` | list[PayloadIndexTelemetry] | Yes | — |  |
