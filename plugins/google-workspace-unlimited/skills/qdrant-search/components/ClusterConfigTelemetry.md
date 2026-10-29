# ClusterConfigTelemetry

**Symbol:** `C_17`

## Description

Fields: grpc_timeout_ms (int); p2p (P2pConfigTelemetry); consensus (ConsensusConfigTelemetry).

## Valid Children

- `C_30` ConsensusConfigTelemetry
- `P_8` P2pConfigTelemetry

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `grpc_timeout_ms` | int | Yes | — |  |
| `p2p` | P2pConfigTelemetry | Yes | — |  |
| `consensus` | ConsensusConfigTelemetry | Yes | — |  |
