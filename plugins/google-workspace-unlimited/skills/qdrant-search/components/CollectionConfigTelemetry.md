# CollectionConfigTelemetry

**Symbol:** `C_9`

## Description

Fields: params (CollectionParams); hnsw_config (HnswConfig); optimizer_config (OptimizersConfig); wal_config (WalConfig); quantization_config (ScalarQuantization | ProductQuantization | BinaryQuantization); strict_mode_config (StrictModeConfigOutput); uuid (UUID); metadata (dict[str, Any]): Arbitrary JSON metadata for the collection.

## Valid Children

- `C_4` CollectionParams
- `Ħ` HnswConfig
- `O_0` OptimizersConfig
- `S_49` StrictModeConfigOutput
- `ü` UUID
- `ʍ` WalConfig

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `params` | CollectionParams | Yes | — |  |
| `hnsw_config` | HnswConfig | Yes | — |  |
| `optimizer_config` | OptimizersConfig | Yes | — |  |
| `wal_config` | WalConfig | Yes | — |  |
| `quantization_config` | Union[ScalarQuantization, ProductQuantization, BinaryQuantization, NoneType] | No | — |  |
| `strict_mode_config` | StrictModeConfigOutput? | No | — |  |
| `uuid` | UUID? | No | — |  |
| `metadata` | dict[str, Any]? | No | — | Arbitrary JSON metadata for the collection |
