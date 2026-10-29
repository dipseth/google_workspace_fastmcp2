# ClusterStatusTelemetry

**Symbol:** `C_19`

## Description

Fields: number_of_peers (int); term (int); commit (int); pending_operations (int); role (StateRole); is_voter (bool); peer_id (int); consensus_thread_status (ConsensusThreadStatusOneOf | ConsensusThreadStatusOneOf1 | ConsensusThreadStatusOneOf2).

## Valid Children

- `ş` StateRole

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `number_of_peers` | int | Yes | — |  |
| `term` | int | Yes | — |  |
| `commit` | int | Yes | — |  |
| `pending_operations` | int | Yes | — |  |
| `role` | StateRole? | No | — |  |
| `is_voter` | bool | Yes | — |  |
| `peer_id` | int? | No | — |  |
| `consensus_thread_status` | Union[ConsensusThreadStatusOneOf, ConsensusThreadStatusOneOf1, ConsensusThreadStatusOneOf2] | Yes | — |  |
