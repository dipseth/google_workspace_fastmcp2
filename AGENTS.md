# Universal Module Wrapping for MCP

## Vision

This project's north star: **any Python module can be wrapped, introspected, indexed, and made callable through MCP tools** — using a compact DSL that LLMs author via natural language. Tiny Recursive Networks (TRM) provide a learned refinement layer that improves search and ranking over time. This is active research — we expect to discover new use cases and patterns along the way.

The proving ground is a Google Workspace MCP server (96 tools, 9 services), but the module wrapping framework is domain-agnostic.

## The Pipeline: Module -> DSL -> MCP

```
Raw Python Module (import path, pip package, or file path)
        |
  1. INTROSPECT — 13 composable mixins walk the module hierarchy,
     |             extract classes/functions/constants as ModuleComponents
     |             (explicit dependency contracts: _MIXIN_PROVIDES, _MIXIN_REQUIRES)
        |
  2. INDEX — Qdrant vector DB stores 3 named vectors per component (RIC schema)
     |        Background pipeline: sync introspection, async embedding + upload
        |
  3. SYMBOLIZE — Unicode symbols auto-assigned per component (§=Section, ᵬ=Button, δ=DecoratedText)
     |             Priority overrides via DomainConfig, module prefixes for disambiguation
        |
  4. SEARCH — Multi-vector semantic search (ColBERT + MiniLM + RRF fusion)
     |          Optional: TRM learned scorer reranks candidates
        |
  5. VALIDATE — Sampling middleware checks DSL syntax, triggers LLM error recovery,
     |            runs validation agents (pre or parallel mode)
        |
  6. EXECUTE — MCP tool call with validated structure, instance patterns stored as feedback
```

Each stage maps to one or more mixins in `adapters/module_wrapper/`. The mixin composition order and dependency contracts are enforced at init time via `validate_mixin_dependencies()`.

## RIC 3-Vector Schema

Every indexed component gets three semantic embeddings, searched via Reciprocal Rank Fusion:

| Vector | Model | Dim | Captures |
|--------|-------|-----|----------|
| `components` | ColBERT | 128D | "What IS this?" — identity, structure, type |
| `inputs` | ColBERT | 128D | "What does it accept?" — parameters, defaults, enums |
| `relationships` | MiniLM | 384D | "How does it connect?" — parent/child, containment, co-occurrence |

Multi-vector search fuses results across all three dimensions: `score = Sum(1 / (k + rank_i))`. Named vectors enable dimension-specific queries when needed.

## DSL Notation

Components get compact Unicode symbols for LLM-friendly authoring:

```
§[δ×3, Ƀ[ᵬ×2]]
= Section containing 3 DecoratedTexts and a ButtonList with 2 Buttons
```

**Syntax elements:** `SYMBOL` (component), `[children]` (nesting), `×N` (multiplicity), `{key=val}` (parameterization), module prefix `g:ᵬ` (disambiguation across wrapped modules).

**Content DSL:** `δ 'Status: Online' success bold` — styled text with modifiers (success, error, bold, italic, etc.), convertible to Jinja2 filters.

**LLM integration:** When an LLM generates invalid DSL, the sampling middleware triggers recovery — injecting all registered DSL docs as context and re-sampling. Validation agents provide semantic checking beyond syntax.

## TRM: The Learning Layer

[Tiny Recursive Models](https://arxiv.org/abs/2510.04871) (Samsung SAIL Montreal) prove that a 2-layer, 7M-param network can outperform Gemini 2.5 Pro on ARC-AGI by recursively refining latent states through the same tiny network. The key insight: **depth through recursion, not parameters**.

### RIC-TRM Mapping

| TRM Concept | RIC Analog | Role |
|-------------|------------|------|
| z_H (answer state) | Components vector | "What IS the current answer" — decodable, interpretable |
| z_L (reasoning state) | Relationships vector | "How things connect" — structural reasoning |
| x (input injection) | Inputs vector | "What goes into it" — parameterization context |
| L_cycles (inner loops) | Multi-vector search passes | Refine latent state through repeated search |
| H_cycles (supervision) | Instance pattern refinement | Outer-loop feedback adjusts inner state |
| Halting (q_head) | Confidence threshold | "Is the answer good enough to stop?" |

### Current State

- **POC** (`research/trm/poc/`): Recursive vector arithmetic showed +9.5% over baseline but hit ceiling (-22% to -28% on harder tasks). Proved the mapping works but arithmetic alone isn't enough.
- **H2 UnifiedTRN** (`research/trm/h2/`): 28.7K-param network with 4 task heads (form, content, pool, halt). V5 features: 17D structural + 384D content. Deployed in card builder slot assignment. 100% validation accuracy on MW domain.
- **Key lesson:** Preserve embedding geometry — compute similarities in the original vector space, then learn a nonlinear combination on top. Never project through random linear layers.

### Next Steps

- Deploy recursive refinement in production search path (multi-cycle `search_hybrid()`)
- Deep supervision: each recursion cycle produces intermediate predictions that contribute to loss
- Expand training data beyond cards/email to new wrapped domains

## Domain Adapters

New modules are wrapped via `DomainConfig` + `WrapperRegistry`:

```python
DomainConfig(
    module_name="card_framework.v2",
    priority_overrides={"Card": 100, "Section": 90, "Button": 85},
    nl_relationship_patterns={("Section", "Button"): "section with button action"},
    post_init_hooks=[register_custom_components],
    post_pipeline_hooks=[create_text_indices],
    dsl_categories={"containers": ["Section", "ButtonList"], "widgets": ["Button", "DecoratedText"]},
)
```

**Active domains:**

| Domain | Module | Collection | Status |
|--------|--------|------------|--------|
| Google Chat cards | `card_framework.v2` | `card_framework_components` | Production |
| Gmail MJML email | `email_framework` | `email_components` | Production |
| Qdrant models | `qdrant_client.models` | `mcp_qdrant_client_models` | Production |

**Adding a new domain:** Create a wrapper setup file (see `gchat/wrapper_setup.py` as template), define `DomainConfig`, register via `WrapperRegistry.register()`, optionally add DSL tool config in `middleware/server_middleware_setup.py`.

## Architectural Principles

- **Mixin composition over inheritance** — 13 mixins with explicit `_MIXIN_PROVIDES` / `_MIXIN_REQUIRES` / `_MIXIN_INIT_ORDER` contracts
- **Preserve embedding geometry** — compute similarities in the original space, learn on top (never random projections)
- **Listwise loss for ranking** — softmax cross-entropy over K candidates, not pairwise BCE
- **Retrieval coverage > scoring sophistication** — if the right candidate isn't retrieved, no scorer can fix it
- **Graceful degradation** — torch is optional; system falls back to RRF fusion without learned scoring
- **Lazy initialization** — Qdrant, embedding models, Rustworkx loaded on-demand
- **Async pipeline** — introspection is sync (fast), Qdrant indexing is background (wrapper usable immediately)
- **Skills auto-generation** — wrapped modules produce markdown skill docs automatically via SkillsMixin

## Key File Map

| Subsystem | Directory | Entry Points |
|-----------|-----------|-------------|
| Module Wrapper core | `adapters/module_wrapper/` | `core.py`, `__init__.py`, `wrapper_factory.py` |
| Mixins (13) | `adapters/module_wrapper/` | `*_mixin.py`, `mixin_meta.py` |
| DSL parser + symbols | `adapters/module_wrapper/` | `dsl_parser.py`, `symbol_generator.py`, `symbols_mixin.py` |
| TRM research | `research/trm/` | `TRM_ANALYSIS.md`, `TRM_MW_ANALYSIS.md` |
| TRM H2 model | `research/trm/h2/` | `unified_trn.py`, `model.py`, `domain_config.py` |
| TRM POC | `research/trm/poc/` | `recursive_search.py`, `ric_vectors.py` |
| Sampling middleware | `middleware/` | `sampling_middleware.py`, `litellm_sampling_handler.py` |
| Sampling prompts | `middleware/sampling_prompts/` | `card_dsl.py`, `email_dsl.py` |
| Domain: GChat cards | `gchat/` | `wrapper_setup.py`, `wrapper_api.py`, `card_builder/slot_assignment.py` |
| Domain: Gmail email | `gmail/` | `email_wrapper_setup.py`, `email_wrapper_api.py` |
| Skills provider | `skills/` | `skills_provider.py`, `server_skill_generator.py` |
| Diagnostic UI | `tools/diagnostic-ui/` | `backend/routes/ml_eval.py`, `frontend/src/components/ml/` |

## Research Status

| Area | Maturity | Notes |
|------|----------|-------|
| MW mixin architecture | Mature | 13 mixins, explicit contracts, 63+ files reference it |
| DSL + sampling integration | Production | Error recovery, validation agents, multi-domain |
| TRM learned scorer | Deployed | UnifiedTRN in slot assignment, 100% val accuracy on MW |
| TRM recursive search | Research | POC works, not yet in production search path |
| New domain adapters | Expansion | Framework ready, needs more domains beyond cards/email/qdrant |

This is discovery work — expect iteration on TRM integration and new domain patterns.

## Agent Configuration Files

- **`.roomodes`** — Defines `riversunlimited-google` mode for Roo Code with Google Workspace integration context
- **`.cursorrules`** — Expertise definitions for Cursor: authentication flows, testing framework, Chat Card Framework v2
