# ClusterTelemetry

**Symbol:** `C_3`

## Description

Fields: enabled (bool); status (ClusterStatusTelemetry); config (ClusterConfigTelemetry); peers (dict[str, PeerInfo]); peer_metadata (dict[str, PeerMetadata]); metadata (dict[str, Any]); resharding_enabled (bool).

## Valid Children

- `C_17` ClusterConfigTelemetry
- `C_19` ClusterStatusTelemetry

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `enabled` | bool | Yes | — |  |
| `status` | ClusterStatusTelemetry? | No | — |  |
| `config` | ClusterConfigTelemetry? | No | — |  |
| `peers` | dict[str, PeerInfo]? | No | — |  |
| `peer_metadata` | dict[str, PeerMetadata]? | No | — |  |
| `metadata` | dict[str, Any]? | No | — |  |
| `resharding_enabled` | bool? | No | — |  |
