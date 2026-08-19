# ClusterStatusOneOf1

**Symbol:** `C_16`

## Description

Description of enabled cluster

## Valid Children

- `ɾ` RaftInfo

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `status` | 'enabled' | Yes | — | Description of enabled cluster |
| `peer_id` | int | Yes | — | ID of this peer |
| `peers` | dict[str, PeerInfo] | Yes | — | Peers composition of the cluster with main information |
| `raft_info` | RaftInfo | Yes | — | Description of enabled cluster |
| `consensus_thread_status` | Union[ConsensusThreadStatusOneOf, ConsensusThreadStatusOneOf1, ConsensusThreadStatusOneOf2] | Yes | — | Description of enabled cluster |
| `message_send_failures` | dict[str, MessageSendErrors] | Yes | — | Consequent failures of message send operations in consensus by peer address. On the first success to send to that peer - entry is removed from this hashmap. |
