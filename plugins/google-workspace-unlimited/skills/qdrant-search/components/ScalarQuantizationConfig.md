# ScalarQuantizationConfig

**Symbol:** `S_32`

## Description

Fields: type (ScalarType); quantile (float): Quantile for quantization. Expected value range in [0.5, 1.0]. If not set - use the whole range of values; always_ram (bool): If true - quantized vectors always will be stored in RAM, ignoring the config of main storage.

## Valid Children

- `♣` ScalarType

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | ScalarType | Yes | — |  |
| `quantile` | float? | No | — | Quantile for quantization. Expected value range in [0.5, 1.0]. If not set - use the whole range of values |
| `always_ram` | bool? | No | — | If true - quantized vectors always will be stored in RAM, ignoring the config of main storage |
