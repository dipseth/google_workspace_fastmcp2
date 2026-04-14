# TRM + Module Wrapper Architecture

## Full Pipeline: Module to Execution

```mermaid
flowchart TB
    subgraph WRAP["1. WRAP (One-time Setup)"]
        direction TB
        MOD["Python Module<br/><i>card_framework.v2<br/>email_blocks<br/>qdrant_client.models</i>"]
        MIX["13 Composable Mixins<br/><i>introspection, cache, symbols,<br/>search, skills, relationships...</i>"]
        MW["ModuleWrapper Instance<br/><i>components, hierarchy,<br/>DAG, symbol map</i>"]

        MOD --> MIX --> MW
    end

    subgraph INDEX["2. INDEX (Async Background)"]
        direction TB

        subgraph EMBED["Embedding Pipelines"]
            E_COMP["components<br/><b>ColBERT 128D multi-vec</b><br/><i>'What IS this?'</i>"]
            E_INP["inputs<br/><b>ColBERT 128D multi-vec</b><br/><i>'What does it accept?'</i>"]
            E_REL["relationships<br/><b>MiniLM 384D dense</b><br/><i>'How does it connect?'</i>"]
            E_CONT["content<br/><b>MiniLM 384D dense</b><br/><i>'What fills it?'</i>"]
        end

        subgraph PAYLOAD["Qdrant Payload (per point)"]
            PL["name, type, full_path,<br/>symbol, docstring,<br/>parent_paths, instance_params,<br/>content_feedback, form_feedback"]
        end

        subgraph STRUCT["Structural Metadata"]
            DAG["Rustworkx DAG<br/><i>parent/child/sibling<br/>depth, ancestors</i>"]
            SYM["Symbol Lexicon<br/><i>Section, Button, DecoratedText<br/> module prefixes g: e:</i>"]
        end

        MW --> EMBED
        MW --> PAYLOAD
        MW --> STRUCT
        EMBED --> QDB[("Qdrant DB<br/><b>4 Named Vectors</b><br/>per component")]
        PAYLOAD --> QDB
    end

    subgraph SEARCH["3. SEARCH (Per Query)"]
        direction TB
        INPUT["User Input<br/><i>description, DSL,<br/>or content text</i>"]

        Q_EMB["Query Embedding<br/><i>ColBERT + MiniLM</i>"]

        PREFETCH["4-Vector Prefetch<br/><i>components + inputs +<br/>relationships + content</i>"]

        RRF["RRF Fusion<br/><i>Reciprocal Rank Fusion<br/>across all 4 vectors</i>"]

        CANDS["~60 Candidates<br/><i>grouped by type:<br/>class, instance_pattern</i>"]

        INPUT --> Q_EMB --> PREFETCH --> RRF --> CANDS
    end

    subgraph TRN["4. TRN SCORING (28.7K params)"]
        direction TB

        subgraph FEAT["Feature Extraction"]
            F_STRUCT["Structural Features (17D)<br/><i>similarities, DAG position,<br/>content density, alignment</i>"]
            F_CONTENT["Content Embedding (384D)<br/><i>query MiniLM vector</i>"]
        end

        subgraph UNIFIED["UnifiedTRN"]
            S_ENC["structural_enc<br/><i>17 -> 32</i>"]
            C_ENC["content_enc<br/><i>384 -> 32</i>"]
            BACK["Shared Backbone<br/><i>64 -> 64 -> 64</i>"]

            subgraph HEADS["4 Task Heads"]
                H_FORM["form_head<br/><i>'Right structure?'</i>"]
                H_CONT["content_head<br/><i>'Right content match?'</i>"]
                H_HALT["halt_head<br/><i>'Stop refining?'</i>"]
                H_POOL["pool_head<br/><i>'Which slot?'</i>"]
            end

            S_ENC --> BACK
            C_ENC --> BACK
            BACK --> HEADS
        end

        CANDS --> FEAT
        F_STRUCT --> S_ENC
        F_CONTENT --> C_ENC
    end

    subgraph RECURSE["5. RECURSIVE REFINEMENT"]
        direction TB
        HALT{"halt_prob > 0.7?"}
        REFINE["RecommendQuery<br/><i>top-5 positive<br/>bottom-3 negative</i>"]
        CONVERGE["Best Scored Results<br/><i>ranked components +<br/>instance patterns</i>"]

        H_HALT --> HALT
        HALT -->|No| REFINE
        REFINE -->|"Next cycle"| CANDS
        HALT -->|Yes| CONVERGE
        H_FORM --> CONVERGE
        H_CONT --> CONVERGE
    end

    subgraph BUILD["6. BUILD (Domain-Specific)"]
        direction TB

        subgraph GENERIC["Generic Layer (MW)"]
            LOOKUP["Component Lookup<br/><i>get_cached_class(name)</i>"]
            INST["Instantiation<br/><i>cls(**valid_params)</i>"]
            SLOT["Slot Assignment<br/><i>pool_head routes content<br/>to correct slots</i>"]
        end

        subgraph DOMAIN["Domain Renderers"]
            R_CHAT["GChat Builder<br/><i>component -> JSON<br/>Google Chat API</i>"]
            R_EMAIL["Email Builder<br/><i>blocks -> MJML<br/>-> HTML</i>"]
            R_NEW["New Domain<br/><i>thin renderer<br/>needed here</i>"]
        end

        CONVERGE --> LOOKUP --> INST
        H_POOL --> SLOT --> INST
        INST --> DOMAIN
    end

    subgraph OUTPUT["7. OUTPUT"]
        O_CARD["Google Chat Card JSON"]
        O_EMAIL["MJML / HTML Email"]
        O_OTHER["Any Module Output"]

        R_CHAT --> O_CARD
        R_EMAIL --> O_EMAIL
        R_NEW --> O_OTHER
    end

    %% Styling
    style WRAP fill:#1a1a2e,stroke:#e94560,color:#fff
    style INDEX fill:#1a1a2e,stroke:#0f3460,color:#fff
    style SEARCH fill:#1a1a2e,stroke:#16213e,color:#fff
    style TRN fill:#1a1a2e,stroke:#e94560,color:#fff
    style RECURSE fill:#1a1a2e,stroke:#533483,color:#fff
    style BUILD fill:#1a1a2e,stroke:#0f3460,color:#fff
    style OUTPUT fill:#1a1a2e,stroke:#16213e,color:#fff

    style QDB fill:#0f3460,stroke:#e94560,color:#fff
    style UNIFIED fill:#533483,stroke:#e94560,color:#fff
    style HEADS fill:#16213e,stroke:#533483,color:#fff
    style GENERIC fill:#16213e,stroke:#0f3460,color:#fff
    style DOMAIN fill:#16213e,stroke:#e94560,color:#fff
```

## Search Mode vs Build Mode

```mermaid
flowchart LR
    subgraph SEARCH_MODE["Search Mode"]
        direction TB
        SM_IN["structural (17D) + content (384D)<br/><i>per candidate features +<br/>query embedding</i>"]
        SM_OUT["form_score + content_score + halt_prob<br/><i>Which candidates match?<br/>Should we stop?</i>"]
        SM_IN --> SM_OUT
    end

    subgraph BUILD_MODE["Build Mode"]
        direction TB
        BM_IN["zeros(17) + content (384D)<br/><i>no structural features,<br/>per-item text embedding</i>"]
        BM_OUT["pool_logits [B, 5]<br/><i>buttons? text? grid?<br/>chips? carousel?</i>"]
        BM_IN --> BM_OUT
    end

    style SEARCH_MODE fill:#1a1a2e,stroke:#e94560,color:#fff
    style BUILD_MODE fill:#1a1a2e,stroke:#0f3460,color:#fff
```

## Domain Agnosticism Breakdown

```mermaid
pie title What's Generic vs Domain-Specific
    "Module Wrapping (generic)" : 25
    "Embedding + Indexing (generic)" : 20
    "Search + TRN Scoring (generic)" : 25
    "Slot Assignment (generic)" : 10
    "Domain Config (thin)" : 5
    "Builder / Renderer (domain-specific)" : 10
    "Output Serialization (domain-specific)" : 5
```

## Adding a New Domain

To wrap a new Python module and make it fully functional:

| Step | Effort | What You Write |
|------|--------|---------------|
| 1. DomainConfig | ~30 lines | Pool vocab, component-to-pool map, specificity order |
| 2. Wrapper setup | ~20 lines | `WrapperRegistry.register(module, config)` |
| 3. Onboarding | 1 command | `python onboard_domain.py --domain new_domain` |
| 4. Domain renderer | ~50-100 lines | **Only domain-specific part**: how to serialize output |

Steps 1-3 are template-driven. Step 4 is the only truly custom code.
