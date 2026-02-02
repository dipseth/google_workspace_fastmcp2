# Relationships & DAG

> **Status:** Coming soon

This document will cover the relationship extraction and DAG-based traversal system.

## Planned Topics

### Relationship Extraction

- Type-hint based extraction
- `Union`, `Optional`, `List` handling
- Manual relationship overrides
- Relationship dict format

### NetworkX DAG

- Graph construction from relationships
- Node attributes (name, symbol, type)
- Edge attributes (containment type)
- Graph statistics

### Traversal Queries

- `get_descendants(node, depth)` - All containable components
- `get_ancestors(node)` - All possible containers
- `get_children(node)` - Direct children only
- `get_parents(node)` - Direct parents only

### Path Queries

- `get_path(source, target)` - Shortest containment path
- `get_all_paths(source, target)` - All possible paths
- `get_path_with_symbols()` - Path as DSL notation

### Containment Checks

- `can_contain(container, component)` - Check if valid
- `validate_containment_chain()` - Validate component sequence
- `get_common_ancestors()` - Find shared containers

### Subgraph Operations

- `get_subgraph(root, depth)` - Extract subtree
- `get_component_neighborhood()` - Local context
- Graph serialization (JSON)

### Analysis

- Root components (no parents)
- Leaf components (no children)
- Hub components (many connections)
- Cycle detection

## Related Files

- `relationships_mixin.py` - RelationshipsMixin implementation
- `graph_mixin.py` - GraphMixin with NetworkX operations
- `structure_validator.py` - Uses relationships for validation
