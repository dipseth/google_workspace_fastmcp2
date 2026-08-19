# ScrollResult

**Symbol:** `▫`

## Description

Result of the points read request

## Valid Children

- `ρ` Record

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `points` | list[Record] | Yes | — | List of retrieved points |
| `next_page_offset` | Union[int[int], str[str], UUID, NoneType] | No | — | Offset which should be used to retrieve a next page result |
