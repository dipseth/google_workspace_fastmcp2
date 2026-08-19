# RaftInfo

**Symbol:** `ɾ`

## Description

Summary information about the current raft state

## Valid Children

- `ş` StateRole
- `ş` StateRole

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `term` | int | Yes | — | Raft divides time into terms of arbitrary length, each beginning with an election. If a candidate wins the election, it remains the leader for the rest of the term. The term number increases monotonically. Each server stores the current term number which is also exchanged in every communication. |
| `commit` | int | Yes | — | The index of the latest committed (finalized) operation that this peer is aware of. |
| `pending_operations` | int | Yes | — | Number of consensus operations pending to be applied on this peer |
| `leader` | int? | No | — | Leader of the current term |
| `role` | StateRole? | No | — | Role of this peer in the current term |
| `is_voter` | bool | Yes | — | Is this peer a voter or a learner |
