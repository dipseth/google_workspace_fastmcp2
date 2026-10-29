# DistributedPeerDetails

**Symbol:** `D_15`

## Description

Fields: version (str): Qdrant version; role (StateRole): Consensus role for the peer; is_voter (bool): Whether it can participate in leader elections; term (int): Election term; commit (int): Latest accepted commit; num_pending_operations (int): Number of operations pending for being applied; consensus_thread_status (ConsensusThreadStatusOneOf | ConsensusThreadStatusOneOf1 | ConsensusThreadStatusOneOf2).

## Valid Children

- `ş` StateRole

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `version` | str | Yes | — | Qdrant version |
| `role` | StateRole? | No | — | Consensus role for the peer |
| `is_voter` | bool | Yes | — | Whether it can participate in leader elections |
| `term` | int | Yes | — | Election term |
| `commit` | int | Yes | — | Latest accepted commit |
| `num_pending_operations` | int | Yes | — | Number of operations pending for being applied |
| `consensus_thread_status` | Union[ConsensusThreadStatusOneOf, ConsensusThreadStatusOneOf1, ConsensusThreadStatusOneOf2] | Yes | — |  |
