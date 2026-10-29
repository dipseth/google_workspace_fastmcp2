# MemoryTelemetry

**Symbol:** `M_2`

## Description

Fields: active_bytes (int): Total number of bytes in active pages allocated by the application; allocated_bytes (int): Total number of bytes allocated by the application; metadata_bytes (int): Total number of bytes dedicated to metadata; resident_bytes (int): Maximum number of bytes in physically resident data pages mapped; retained_bytes (int): Total number of bytes in virtual memory mappings.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `active_bytes` | int | Yes | — | Total number of bytes in active pages allocated by the application |
| `allocated_bytes` | int | Yes | — | Total number of bytes allocated by the application |
| `metadata_bytes` | int | Yes | — | Total number of bytes dedicated to metadata |
| `resident_bytes` | int | Yes | — | Maximum number of bytes in physically resident data pages mapped |
| `retained_bytes` | int | Yes | — | Total number of bytes in virtual memory mappings |
