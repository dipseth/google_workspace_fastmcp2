# DistributedPeerInfo

**Symbol:** `D_14`

## Description

Fields: uri (str): URI of the peer; responsive (bool): Whether this peer responded for this request; details (DistributedPeerDetails): If responsive, these details should be available.

## Valid Children

- `D_15` DistributedPeerDetails

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `uri` | str | Yes | — | URI of the peer |
| `responsive` | bool | Yes | — | Whether this peer responded for this request |
| `details` | DistributedPeerDetails? | No | — | If responsive, these details should be available |
