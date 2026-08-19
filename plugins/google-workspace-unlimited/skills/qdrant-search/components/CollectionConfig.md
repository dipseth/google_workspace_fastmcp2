# CollectionConfig

**Symbol:** `C_1`

## Description

Information about the collection configuration

## Valid Children

- `C_4` CollectionParams
- `Ħ` HnswConfig
- `O_0` OptimizersConfig
- `ʍ` WalConfig
- `S_49` StrictModeConfigOutput
- `C_4` CollectionParams
- `Ħ` HnswConfig
- `O_0` OptimizersConfig
- `ʍ` WalConfig
- `S_49` StrictModeConfigOutput
- ... and 5 more

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `params` | CollectionParams | Yes | — | Information about the collection configuration |
| `hnsw_config` | HnswConfig | Yes | — | Information about the collection configuration |
| `optimizer_config` | OptimizersConfig | Yes | — | Information about the collection configuration |
| `wal_config` | WalConfig? | No | — | Information about the collection configuration |
| `quantization_config` | Union[ScalarQuantization, ProductQuantization, BinaryQuantization, NoneType] | No | — | Information about the collection configuration |
| `strict_mode_config` | StrictModeConfigOutput? | No | — | Information about the collection configuration |
| `metadata` | dict[str, Any]? | No | — | Arbitrary JSON metadata for the collection This can be used to store application-specific information such as creation time, migration data, inference model info, etc. |
