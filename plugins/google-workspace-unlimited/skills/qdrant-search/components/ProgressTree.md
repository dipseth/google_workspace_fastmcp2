# ProgressTree

**Symbol:** `▪`

## Description

Fields: name (str): Name of the operation.; started_at (datetime | date): When the operation started.; finished_at (datetime | date): When the operation finished.; duration_sec (float): For finished operations, how long they took, in seconds.; done (int): Number of completed units of work, if applicable.; total (int): Total number of units of work, if applicable and known.; children (list[ProgressTree]): Child operations..

## Valid Children

- `▪` ProgressTree

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | str | Yes | — | Name of the operation. |
| `started_at` | Union[datetime, date, NoneType] | No | — | When the operation started. |
| `finished_at` | Union[datetime, date, NoneType] | No | — | When the operation finished. |
| `duration_sec` | float? | No | — | For finished operations, how long they took, in seconds. |
| `done` | int? | No | — | Number of completed units of work, if applicable. |
| `total` | int? | No | — | Total number of units of work, if applicable and known. |
| `children` | list[ProgressTree]? | No | — | Child operations. |
