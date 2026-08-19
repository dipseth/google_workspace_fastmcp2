# CollectionInfo

**Symbol:** `◘`

## Description

Current statistics and configuration of the collection

## Valid Children

- `C_5` CollectionStatus
- `C_11` CollectionWarning
- `C_1` CollectionConfig
- `U_4` UpdateQueueInfo
- `C_5` CollectionStatus
- `C_11` CollectionWarning
- `C_1` CollectionConfig
- `U_4` UpdateQueueInfo

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `status` | CollectionStatus | Yes | — | Current statistics and configuration of the collection |
| `optimizer_status` | Union[OptimizersStatusOneOf, OptimizersStatusOneOf1] | Yes | — | Current statistics and configuration of the collection |
| `warnings` | list[CollectionWarning]? | No | — | Warnings related to the collection |
| `indexed_vectors_count` | int? | No | — | Approximate number of indexed vectors in the collection. Indexed vectors in large segments are faster to query, as it is stored in a specialized vector index. |
| `points_count` | int? | No | — | Approximate number of points (vectors + payloads) in collection. Each point could be accessed by unique id. |
| `segments_count` | int | Yes | — | Number of segments in collection. Each segment has independent vector as payload indexes |
| `config` | CollectionConfig | Yes | — | Current statistics and configuration of the collection |
| `payload_schema` | dict[str, PayloadIndexInfo] | Yes | — | Types of stored payload |
| `update_queue` | UpdateQueueInfo? | No | — | Update queue info |
