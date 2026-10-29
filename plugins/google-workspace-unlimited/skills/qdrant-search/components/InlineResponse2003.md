# InlineResponse2003

**Symbol:** `I_14`

## Description

Fields: usage (Usage); time (float): Time spent to process this request; status (str); result (ClusterStatusOneOf | ClusterStatusOneOf1).

## Valid Children

- `ʊ` Usage

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `usage` | Usage? | No | — |  |
| `time` | float? | No | — | Time spent to process this request |
| `status` | str? | No | — |  |
| `result` | Union[ClusterStatusOneOf, ClusterStatusOneOf1, NoneType] | No | — |  |
