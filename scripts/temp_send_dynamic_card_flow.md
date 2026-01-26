# send_dynamic_card Complete Flow Diagram

> **Note:** force_reindex_components

## Complete Mermaid Diagram

```mermaid
flowchart TD
    subgraph MCP["🔧 MCP Tool: send_dynamic_card"]
        PARAMS["Parameters:<br/>• user_google_email*<br/>• space_id*<br/>• card_description*<br/>• card_params<br/>• thread_key<br/>• webhook_url"]
    end
    
    PARAMS --> SCB["SmartCardBuilder<br/>build_card_from_description()"]
    
    subgraph SMART["SmartCardBuilder (Primary Path)"]
        SCB --> STRICT{strict_mode?}
        STRICT -->|Yes| EXPLICIT["Build from<br/>explicit params only"]
        
        STRICT -->|No| GRID{grid or<br/>images?}
        GRID -->|Yes| GRID_CARD["_build_grid_card()"]
        
        GRID -->|No| SECTIONS{explicit<br/>sections?}
        SECTIONS -->|Yes| SECTION_CARD["_build_card_from_explicit_sections()"]
        
        SECTIONS -->|No| FEEDBACK["_get_proven_params()"]
        
        subgraph QDRANT1["🔍 Qdrant: Feedback Loop"]
            FEEDBACK --> Q1["Query mcp_gchat_cards_v7<br/>for proven patterns"]
        end
        
        FEEDBACK --> PATTERNS["_find_similar_patterns()"]
        
        subgraph QDRANT2["🔍 Qdrant: Pattern Search"]
            PATTERNS --> Q2["_search_by_identity()<br/>ColBERT → 'components' vector"]
            Q2 --> Q2_ENRICH["Enrich with full payload:<br/>instance_params, parent_paths"]
        end
        
        PATTERNS --> STRUCT["StructureValidator<br/>generate_structure_from_inputs()"]
        
        STRUCT --> TEMPLATE["_find_matching_template()"]
        
        subgraph QDRANT3["🔍 Qdrant: Template Search"]
            TEMPLATE --> Q3["Query promoted templates<br/>'relationships' vector"]
        end
        
        TEMPLATE --> NL_PARSE["Parse NL description<br/>into sections/widgets"]
        
        NL_PARSE --> RENDER["_render_card()"]
        
        subgraph QDRANT4["🔍 Qdrant: Component Loading"]
            RENDER --> Q4["_search_by_relationships()<br/>MiniLM → 'relationships' vector<br/>(symbol-enriched embeddings)"]
            Q4 --> LOAD["ModuleWrapper.get_component_by_path()"]
        end
    end
    
    EXPLICIT --> CARD_OUT["Card JSON"]
    GRID_CARD --> CARD_OUT
    SECTION_CARD --> CARD_OUT
    RENDER --> CARD_OUT
    
    CARD_OUT --> CHECK{Card<br/>created?}
    
    CHECK -->|No| FALLBACK["_build_simple_card_structure()<br/>(No Qdrant - basic card)"]
    
    CHECK -->|Yes| SEND["Send to Google Chat"]
    FALLBACK --> SEND
    
    SEND --> API{webhook_url?}
    API -->|Yes| WEBHOOK["POST to Webhook"]
    API -->|No| GCHAT_API["Google Chat API<br/>spaces.messages.create()"]
    
    WEBHOOK --> RESPONSE["SendDynamicCardResponse"]
    GCHAT_API --> RESPONSE
    
    style QDRANT1 fill:#e1f5fe,stroke:#01579b
    style QDRANT2 fill:#e1f5fe,stroke:#01579b
    style QDRANT3 fill:#e1f5fe,stroke:#01579b
    style QDRANT4 fill:#e1f5fe,stroke:#01579b
    style FALLBACK fill:#fff3e0,stroke:#e65100
```

## Key Points

### All primary paths use Qdrant:

1. **Feedback Loop** → queries proven patterns from successful cards
2. **Pattern Search** → `_search_by_identity()` with ColBERT multi-vector on `components` named vector
3. **Template Search** → queries promoted templates via `relationships` vector
4. **Component Loading** → `_search_by_relationships()` with MiniLM on `relationships` vector (this is where symbol-enriched embeddings match DSL notation)

### Only fallback bypasses Qdrant:

- `_build_simple_card_structure()` is only used if SmartCardBuilder throws an exception - it builds a basic text/button card without any vector search

### DSL symbols work via vector similarity:

- The v7 collection's `relationships` vector contains symbol-enriched text like:
  - `§ Section | contains C_0 CollapseControl, ʍ Widget | §[C_0, ʍ]`
  - `Ƀ ButtonList | contains ᵬ Button | Ƀ[ᵬ]`
- When you pass `§[δ, Ƀ[ᵬ×2]] Dashboard` as `card_description`, the MiniLM embedding matches against these symbol patterns

---

✻ *Cooked for 1m 9s*
