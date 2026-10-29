# RunningEnvironmentTelemetry

**Symbol:** `R_13`

## Description

Fields: distribution (str); distribution_version (str); is_docker (bool); cores (int); ram_size (int); disk_size (int); cpu_flags (str); cpu_endian (CpuEndian); gpu_devices (list[GpuDeviceTelemetry]).

## Valid Children

- `©` CpuEndian
- `G_6` GpuDeviceTelemetry

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `distribution` | str? | No | — |  |
| `distribution_version` | str? | No | — |  |
| `is_docker` | bool | Yes | — |  |
| `cores` | int? | No | — |  |
| `ram_size` | int? | No | — |  |
| `disk_size` | int? | No | — |  |
| `cpu_flags` | str | Yes | — |  |
| `cpu_endian` | CpuEndian? | No | — |  |
| `gpu_devices` | list[GpuDeviceTelemetry]? | No | — |  |
