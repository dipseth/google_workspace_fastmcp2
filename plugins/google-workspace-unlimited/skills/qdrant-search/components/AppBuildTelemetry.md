# AppBuildTelemetry

**Symbol:** `ă`

## Description

Fields: name (str); version (str); features (AppFeaturesTelemetry); runtime_features (FeatureFlags); hnsw_global_config (HnswGlobalConfig); system (RunningEnvironmentTelemetry); jwt_rbac (bool); hide_jwt_dashboard (bool); startup (datetime | date).

## Valid Children

- `A_2` AppFeaturesTelemetry
- `F_0` FeatureFlags
- `ɦ` HnswGlobalConfig
- `R_13` RunningEnvironmentTelemetry

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | str | Yes | — |  |
| `version` | str | Yes | — |  |
| `features` | AppFeaturesTelemetry? | No | — |  |
| `runtime_features` | FeatureFlags? | No | — |  |
| `hnsw_global_config` | HnswGlobalConfig? | No | — |  |
| `system` | RunningEnvironmentTelemetry? | No | — |  |
| `jwt_rbac` | bool? | No | — |  |
| `hide_jwt_dashboard` | bool? | No | — |  |
| `startup` | Union[datetime, date] | Yes | — |  |
