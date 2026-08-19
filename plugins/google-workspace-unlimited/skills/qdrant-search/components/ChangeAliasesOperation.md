# ChangeAliasesOperation

**Symbol:** `C_25`

## Description

Operation for performing changes of collection aliases. Alias changes are atomic, meaning that no collection modifications can happen between alias operations.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `actions` | list[Union[CreateAliasOperation, DeleteAliasOperation, RenameAliasOperation]] | Yes | — | Operation for performing changes of collection aliases. Alias changes are atomic, meaning that no collection modifications can happen between alias operations. |
