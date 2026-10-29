# CollectionParamsDiff

**Symbol:** `C_28`

## Description

Fields: replication_factor (int): Number of replicas for each shard; write_consistency_factor (int): Minimal number successful responses from replicas to consider operation successful; read_fan_out_factor (int): Fan-out every read request to these many additional remote nodes (and return first available response); read_fan_out_delay_ms (int): Delay in milliseconds before sending read requests to remote nodes; on_disk_payload (bool): If true - point&#x27;s payload will not be stored in memory. It will be read from the disk every time it is requested. This setting saves RAM by (slightly) increasing the response time. Note: those payload values that are involved in filtering and are indexed - remain in RAM..

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `replication_factor` | int? | No | — | Number of replicas for each shard |
| `write_consistency_factor` | int? | No | — | Minimal number successful responses from replicas to consider operation successful |
| `read_fan_out_factor` | int? | No | — | Fan-out every read request to these many additional remote nodes (and return first available response) |
| `read_fan_out_delay_ms` | int? | No | — | Delay in milliseconds before sending read requests to remote nodes |
| `on_disk_payload` | bool? | No | — | If true - point&#x27;s payload will not be stored in memory. It will be read from the disk every time it is requested. This setting saves RAM by (slightly) increasing the response time. Note: those payload values that are involved in filtering and are indexed - remain in RAM. |
