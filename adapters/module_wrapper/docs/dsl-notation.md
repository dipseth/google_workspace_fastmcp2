# DSL Notation

> **Status:** Coming soon

This document will cover the Domain-Specific Language (DSL) for representing component structures.

## Planned Topics

### Symbol Table

- Unicode symbol assignment rules
- Component → Symbol mapping
- Module prefix symbols
- Fallback symbol generation

### DSL Syntax

- Basic syntax: `SYMBOL[children]`
- Multiplicity: `ᵬ×2` (2 buttons)
- Nesting: `§[δ, Ƀ[ᵬ×2]]`
- Separator conventions

### Common Patterns

| Pattern | Meaning |
|---------|---------|
| `§[δ]` | Section with DecoratedText |
| `§[δ, Ƀ[ᵬ×2]]` | Section with text and 2 buttons |
| `§[ℊ[ǵ×4]]` | Section with 4-item grid |
| `§[δ×3]` | Section with 3 text items |

### DSL Parsing

- `parse_dsl_to_components()` - Parse DSL to structure
- `build_dsl_from_paths()` - Generate DSL from component list
- `extract_dsl_from_text()` - Extract DSL from natural language
- `instantiate_from_dsl()` - Create component instances

### Structure Validation

- Containment rule validation
- Invalid structure detection
- Validation result format

### Embedding Integration

- DSL in embedding text
- Symbol wrapping for ColBERT
- DSL-aware search queries

## Related Files

- `symbols_mixin.py` - SymbolsMixin implementation
- `symbol_generator.py` - Symbol generation logic
- `dsl_parser.py` - DSL parsing utilities
- `structure_validator.py` - Structure validation
