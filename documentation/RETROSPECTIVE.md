# Retrospective: The Card Builder Journey

```
           ___
          /   \        "We didn't build a card builder.
         | o o |        We grew one."
          \ - /
           | |              _______________
           | |             /               \
     ______|_|______      | From hardcoded  |
    /               \     | symbols to a    |
   | iteration  1   |     | self-describing |
   | iteration  2   |     | graph that      |
   | iteration  3   |     | teaches itself  |
   | iteration  4   |---->| new tricks.     |
   | .............. |      \_______________/
   |   finally.     |
    \_______________/
```

---

## The Numbers

```
  Card Builder + Module Wrapper
  =============================

  24  Python files in adapters/module_wrapper/
  15  Python files in gchat/card_builder/
   1  card_framework_wrapper.py (the glue)
  ─────────────────────────────────
  ~42,000 lines of code
  38 commits touching this surface area
  6 major PRs (#19 → #24)
```

---

## Where We Started

The original `SMART_CARD_BUILDER_ARCHITECTURE.md` tells the story of v1:

```
  User Input ──> NLP Parser ──> Qdrant Search ──> ModuleWrapper ──> .render() ──> JSON
```

It was clean in theory. In practice:

- **Hardcoded component names** everywhere: `"TextInput"`, `"DecoratedText"`, `"ButtonList"`
- **Hardcoded symbols**: `§`, `δ`, `Ƀ` baked into string literals
- **NLP parsers** that extracted form fields with regex chains
- **Qdrant was a lookup table**, not a knowledge base
- Components were loaded one-by-one, no understanding of relationships

```
   v1 Architecture (simplified)
   ============================

   "Create a form card"
          |
          v
   regex: /text input named (\w+)/
          |
          v
   qdrant.search("TextInput")     <-- literal string match
          |
          v
   ModuleWrapper.get_component_by_path()
          |
          v
   TextInput(name="x", label="y").render()
```

It worked. For the 5 card types the NLP parser knew about.

---

## The Frustrating Middle (Iterations 2-3)

```
          ┌────────────────────────────┐
          │  "Why do we keep building  │
          │   NLP parsers that don't   │
          │   actually use Qdrant?"    │
          │                            │
          │   We had a vector DB.      │
          │   We had embeddings.       │
          │   But we kept writing      │
          │   if/elif chains.          │
          └────────────────────────────┘
```

The second and third attempts tried to be smarter about NLP but kept falling
into the same trap:

1. Write a better regex/NLP parser
2. Map parsed tokens to component names
3. Search Qdrant with those names
4. Build components with hardcoded params

**The Qdrant search was decoration.** The real logic was still in Python
string matching. We'd add a new card type, discover the NLP parser
couldn't handle it, add more regex, and the cycle repeated.

The symbol mapping was the worst offender. Symbols like `§` and `δ` were
hardcoded in:
- `builder_v2.py` (the builder)
- `dsl.py` (the parser)
- `card_tools.py` (the MCP tool)
- Test files
- Documentation

Change one symbol and you'd break three files.

---

## The Breakthrough: "Never Hardcode Symbols"

```
   ┌─────────────────────────────────────────────┐
   │                                             │
   │   "The symbols should come FROM the graph,  │
   │    not be baked INTO the code."              │
   │                                             │
   │   That single constraint changed everything.│
   │                                             │
   └─────────────────────────────────────────────┘
```

This was the design principle that unlocked iteration 4:

- **SymbolGenerator** creates unique Unicode symbols from component names
- **DSLParser** reads symbols from the wrapper, not from constants
- **`card_framework_wrapper.py`** is the singleton that hands symbols to everyone
- **`get_gchat_symbols()`** is the one source of truth

If a new component appears in `card_framework`, it automatically gets a symbol,
shows up in DSL parsing, and becomes available in search — **zero code changes**.

---

## NetworkX: The Game Changer

```
         Card
        / | \
       /  |  \
   Header Section Footer
            |
     ┌──────┼──────┐
     |      |      |
   Widget Widget Widget
     |              |
  DecoratedText  ButtonList
     |              |
   [Icon]        [Button]
     |              |
  startIcon      [OnClick]
                    |
                 [OpenLink]
```

Adding **NetworkX** as a directed acyclic graph (DAG) for component
relationships was transformative:

- **`can_contain(parent, child)`** — validated at build time, not runtime errors
- **`get_field_for_child(parent, child)`** — generic child mapping, no if/elif
- **`_find_required_wrapper_via_dag()`** — auto-wrap Button in ButtonList
- **52 components, 68+ edges** — all discoverable, all queryable

Before NetworkX, the builder had methods like:
```python
if component_name == "DecoratedText":
    if child_name == "Button":
        params["button"] = built_child
    elif child_name == "Icon":
        params["startIcon"] = built_child
    elif child_name == "SwitchControl":
        params["switchControl"] = built_child
```

After NetworkX:
```python
field_info = wrapper.get_field_for_child(parent_name, child_name)
params[field_info["field_name"]] = built_child
```

**One line replaced dozens of special cases.**

---

## The Architecture Now (v2)

```
   v2 Architecture
   ===============

   Input (any of):
   ├── DSL:    "§[δ[ᵬ], Ƀ[ᵬ×2]]"
   ├── NL:     "card with buttons"
   ├── URL:    "check out https://github.com/..."
   ├── Params: {title, text, buttons, items}
   └── Pre-built: {sections: [{widgets: [...]}]}
          |
          v
   ┌─ card_tools.py ──────────────────────────┐
   │  URL extraction → buttons                 │
   │  suggest_dsl_for_params()                 │
   │  Qdrant instance pattern reuse            │
   │  Pre-built sections passthrough           │
   └──────────────────────────────────────────┘
          |
          v
   ┌─ SmartCardBuilderV2 ─────────────────────┐
   │  DSL parse → structure tree               │
   │  Context consumption (sequential)         │
   │  _build_widget_generic()                  │
   │  _map_children_to_params() via DAG        │
   │  _build_component() via wrapper cache     │
   │  Feedback loop storage                    │
   └──────────────────────────────────────────┘
          |
          v
   ┌─ ModuleWrapper (24 files, ~17K lines) ───┐
   │  SymbolGenerator (dynamic symbols)        │
   │  DSLParser (symbol-aware tokenization)    │
   │  StructureValidator (DAG-based)           │
   │  GraphMixin (NetworkX DAG)                │
   │  SearchMixin (ColBERT + MiniLM + BM25)   │
   │  RelationshipsMixin (parent→child edges)  │
   │  CacheMixin (L1 memory cache)             │
   │  RIC Provider (relationship indexing)     │
   └──────────────────────────────────────────┘
          |
          v
   ┌─ card_framework ─────────────────────────┐
   │  52 components with .render() / .to_dict()│
   │  Automatic relationship extraction        │
   │  Widget → JSON conversion                 │
   └──────────────────────────────────────────┘
          |
          v
   ┌─ Qdrant ─────────────────────────────────┐
   │  3-vector schema (inputs, components,     │
   │    relationships)                         │
   │  Instance patterns with feedback          │
   │  Discovery API for pattern reuse          │
   │  V7 schema with background pipeline       │
   └──────────────────────────────────────────┘
```

---

## What Went Well

### 1. The Abstraction Discipline
Refusing to hardcode symbols forced every layer to be dynamic. The result
is a system where you can wrap **any Python module** — not just card_framework —
and get symbols, DAG, search, and DSL for free.

### 2. NetworkX as the Source of Truth
The DAG replaced hundreds of lines of conditional logic with graph queries.
Validation, child mapping, auto-wrapping — all derived from edges.

### 3. Qdrant as a Living Knowledge Base
Instance patterns with feedback scores mean the system gets better with use.
The V7 schema (3 vectors: inputs, components, relationships) enables genuinely
different search strategies depending on what you're looking for.

### 4. Context Consumption Pattern
The sequential consumption model (`_text_index`, `_button_index`) elegantly
solved the "which button goes where" problem in complex DSL like
`§[δ[ᵬ], Ƀ[ᵬ×2]]` — first button to DecoratedText, next two to ButtonList.

### 5. Creative Breaks
Writing poetry in module docstrings wasn't just fun — it kept the
mindset abstract and prevented premature concreteness. When you're writing
a haiku about relationships between components, you're thinking about the
*shape* of the system, not the implementation details.

---

## What Was Frustrating

### 1. Three False Starts
It took 3-4 iterations to stop building NLP parsers and start building
infrastructure. Each time we'd write a parser, realize it couldn't
generalize, and start over. The sunk cost was real.

### 2. The OnClick Cache Bug (Today!)
`get_cached_class("OnClick")` resolved to `card_framework.v2.card.OnClick`
instead of `card_framework.v2.widgets.on_click.OnClick`. A wrong path in
the resolver meant **no buttons rendered in nested DSL for who knows how
long**. One wrong string, invisible failure, silent degradation.

### 3. Chip Auto-Wrap Still Open
Bare `Chip` widgets at the section level cause 400 errors from Google Chat.
The DAG knows chips need ChipList wrapping, but the builder doesn't always
enforce it. The infrastructure is there; the wiring isn't complete.

---

## The Emotional Arc

```
   Excitement ─────┐
                   │     "This is going
                   │      to be amazing"
                   │
                   │                              ┌─── "Wait, it
                   │                              │     actually works"
                   │                              │
                   └──┐                     ┌─────┘
                      │                     │
                      │     "Why doesn't    │
                      │      Qdrant help    │
                      │      at all?"       │
                      │         │           │
                      └────┐    │    ┌──────┘
                           │    │    │
   Frustration ────────────┴────┘────┘

   PR #19        #21        #22       #23        #24       Today
   "module       "card      "FastMCP  "V7        "RIC      "Nested DSL
    wrapper       builder    v3 rc2    schema     provider   fixed +
    basics"       v2"        upgrade"  + DAG"     + tests"   URL auto"
```

---

## Lessons Learned

```
  ┌──────────────────────────────────────────────────┐
  │                                                  │
  │  1. Abstractions beat parsers.                   │
  │     A good graph is worth a thousand regexes.    │
  │                                                  │
  │  2. Never hardcode what can be derived.          │
  │     Symbols, relationships, field names —        │
  │     all should flow from the source.             │
  │                                                  │
  │  3. Silent failures are the worst failures.      │
  │     The OnClick bug taught us: when a cache      │
  │     miss returns None, don't just skip —         │
  │     have a fallback path.                        │
  │                                                  │
  │  4. Qdrant is for learning, not just lookup.     │
  │     Instance patterns with feedback turn a       │
  │     static search into an improving system.      │
  │                                                  │
  │  5. Creative constraints spark creative          │
  │     solutions. "Never hardcode symbols" felt     │
  │     limiting but produced the most flexible      │
  │     architecture we could have designed.         │
  │                                                  │
  └──────────────────────────────────────────────────┘
```

---

## Things I'd Also Think About

*These are observations from sitting inside the codebase — patterns,
risks, and design decisions worth naming even if they worked out.*

### 6. The ModuleWrapper Is Bigger Than Cards

```
   card_framework  ←── ModuleWrapper ──→  ???
                                          ┊
                                     Any Python module
                                     with classes and
                                     relationships.
```

The 24-file module wrapper system is **domain-agnostic**. It doesn't know
about Google Chat. It knows about Python modules, class hierarchies,
NetworkX graphs, Qdrant vectors, and DSL symbols. The `card_framework_wrapper.py`
is the thin seam that injects Google Chat-specific knowledge (NL relationship
patterns, component metadata, widget introspection).

That means this same infrastructure could wrap a Django models module, a
protobuf schema, a state machine library — anything with typed classes and
parent-child relationships. The fact that it works for cards is almost
incidental. **This is a general-purpose module introspection and search engine.**
That's worth protecting — resist the urge to leak card-specific logic
into the wrapper itself.

### 7. The Mixin Architecture: Power and Peril

```
   ModuleWrapper inherits from:
   ├── ModuleWrapperBase
   ├── QdrantMixin
   ├── EmbeddingMixin
   ├── IndexingMixin
   ├── SearchMixin
   ├── CacheMixin
   ├── RelationshipsMixin
   ├── GraphMixin
   ├── PipelineMixin
   ├── InstancePatternMixin
   └── SkillsMixin
```

11 mixins. Each one is testable in isolation. Each one adds a capability.
But the composition means **any method can call any other mixin's method**
through `self`. The call graph is implicit. When `SearchMixin.search_hybrid()`
calls `self.embed_text()` (from `EmbeddingMixin`) and `self.client` (from
`QdrantMixin`), the dependency is invisible at the file level.

This worked because one person held the whole mental model. It would
benefit from a dependency diagram or an explicit `__init__` that wires
capabilities together, so the next developer can trace flows without
reading all 11 files.

### 8. The Feedback Loop Is Reinforcement Learning

```
   ┌──────────┐     ┌──────────┐     ┌──────────┐
   │  Build   │────>│  Deliver │────>│  User    │
   │  Card    │     │  via     │     │  Sees    │
   │          │     │  Webhook │     │  Card    │
   └──────────┘     └──────────┘     └────┬─────┘
        ^                                 │
        │                                 v
   ┌────┴─────┐                    ┌──────────┐
   │  Qdrant  │<───────────────────│ Feedback │
   │  Bias    │   positive/        │ Button   │
   │  Search  │   negative         │ Click    │
   └──────────┘                    └──────────┘
```

This is human-in-the-loop reinforcement learning, implemented without
any ML framework. Positive feedback biases future searches toward that
pattern. Negative feedback demotes it. Over time, the system converges
on structures users actually want.

**The risk**: if early patterns are noisy (lots of `§[δ]` from test runs),
the system anchors on simplicity. The cleanup logic (which we just fixed)
is load-bearing — without it, stale patterns crowd out good ones. The
`content_feedback` index error meant cleanup was silently failing,
which is why patterns grew to 733 (well past the 500 limit).

### 9. The 2000-Line Seam

`card_framework_wrapper.py` is ~2000 lines and is the most architecturally
critical file in the system. It:

- Creates the singleton ModuleWrapper instance
- Registers all card component metadata (resources, containers, wrappers)
- Registers behavioral relationships from `GCHAT_NL_RELATIONSHIP_PATTERNS`
- Indexes custom components to Qdrant
- Exposes `get_dsl_parser()`, `get_gchat_symbols()`, `extract_dsl_from_description()`
- Runs DAG warm-start recipes

If this file breaks, everything breaks. It's the gravitational center.
Worth considering whether it should be split into:
- `wrapper_setup.py` (initialization, metadata registration)
- `wrapper_api.py` (public functions other modules call)
- `wrapper_dag.py` (warm-start, relationship registration)

### 10. Silent Degradation Is the Pattern

Today's OnClick bug is an instance of a **recurring theme**:

```
   Component X not in cache
        │
        v
   get_cached_class() returns None
        │
        v
   Caller checks `if not all([A, B, C]):`
        │
        v
   Returns None (silently)
        │
        v
   Parent widget renders without child
        │
        v
   Card looks "mostly fine" but missing pieces
        │
        v
   Nobody notices for weeks
```

This happened with:
- OnClick → no buttons in nested DSL
- DecoratedText → missing text field
- Chip → bare widget at section level (still open)
- `content_feedback` index → cleanup silently failing

The system is **too graceful**. When something fails, it degrades to a
simpler card instead of raising. For production delivery that's correct
(better to send *something* than crash). But for development, there
should be a "strict mode" that fails loudly on any None-returns from
component resolution. Consider a `CARD_BUILDER_STRICT=true` env var
that turns silent None-returns into logged warnings with full tracebacks.

### 11. The Complexity Budget

```
   42,000 lines across card builder + module wrapper

   For context:
   ├── Flask framework:          ~15,000 lines
   ├── FastAPI framework:        ~20,000 lines
   └── This card builder:        ~42,000 lines
```

This isn't necessarily bad — the system does a lot (introspection, DAG,
3-vector search, DSL parsing, context consumption, feedback, caching).
But it means the **onboarding cost is real**. A new developer would need
to understand:

1. How mixins compose into ModuleWrapper
2. How the DAG relates to Qdrant vectors
3. How DSL symbols flow from SymbolGenerator through DSLParser to builder
4. How context consumption distributes params across widgets
5. How the feedback loop biases search results

The architecture doc helps. The poetry helps (seriously — it signals
"this is meant to be understood at a conceptual level"). But the single
most valuable thing for onboarding would be a **10-minute walkthrough of
building one card end-to-end**, annotated with which file/function handles
each step. The mermaid diagrams in the architecture doc are close but
they describe v1 flows, not the current v2 DSL-first path.

### 12. What I'd Protect

If I had to pick three things to never regress:

1. **Dynamic symbols** — the moment someone hardcodes `§` in a new file,
   the abstraction starts leaking. Lint for it.

2. **DAG-driven child mapping** — `get_field_for_child()` is the single
   most leveraged function. Every new component relationship should go
   through the graph, never through a new if/elif.

3. **Context consumption ordering** — the sequential `_text_index`,
   `_button_index` model is simple and correct. It would be tempting
   to make it "smarter" (semantic matching of buttons to widgets). Don't.
   Sequential is predictable and debuggable.

---

## Looking Forward

The foundation is solid. The open items are *wiring* problems, not
*architecture* problems:

- **Chip auto-wrap** → DAG knows the answer, builder just needs to ask
- **Image URL heuristics** → Pattern matching at the extraction layer
- **Jinja + URL ordering** → Sequence the preprocessing pipeline
- **NL-only pattern quality** → More diverse patterns + feedback = better search

The system we have now can represent, search, build, validate, and deliver
any Google Chat card structure — from a single text line to a deeply nested
DSL tree — using the same code path. That's not where we started.

```
                    *
                   ***
                  *****         It's a tree now.
                 *******        It has roots (Qdrant).
                *********       Branches (DAG).
               ***********      Leaves (widgets).
              *************     And it grows.
                  |||
                  |||
            ──────┴┴┴──────
```

---

## Action Items & Follow-Up (2025-02-25 Session)

*Added after implementing `CARD_BUILDER_STRICT` mode and reviewing the
retrospective end-to-end.*

### Done

- [x] **CARD_BUILDER_STRICT mode** (item #10) — Implemented.
  `CARD_BUILDER_STRICT=1` env var instruments 7 degradation sites across
  `cache_mixin.py`, `rendering.py`, and `builder_v2.py`. Each silent
  None-return now emits a `WARNING` with `[STRICT]` prefix and full
  traceback via `adapters/module_wrapper/strict.py`. Production behavior
  unchanged. Logger `card_builder.strict` is filterable.

- [x] **Hardcoded symbol lint** (item #12, bullet 1) — Already landed in
  commit `5e7ac50`. Lint check catches hardcoded DSL symbols in new files.

- [x] **Wrapper seam split** (item #9) — Verified complete.
  `card_framework_wrapper.py` → 106-line re-export facade. Actual logic
  lives in `wrapper_setup.py` (711 lines), `wrapper_api.py` (1106 lines),
  `wrapper_dag.py` (139 lines). All 30 importers use the facade. No
  migration work needed — the split was already finished.

- [x] **v2 end-to-end walkthrough** (item #11) — Added below as
  "Appendix: v2 Build Trace". Annotated trace from DSL input to Google
  Chat JSON, replacing the v1 mermaid diagrams as the onboarding artifact.

- [x] **DAG-bypass lint** (item #12, bullet 2) — `scripts/lint_no_dag_bypass.py`
  detects `if component_name ==` patterns in builder files. DSL002 rule,
  WARNING-only (existing 13 occurrences are legitimate special cases).
  Added to CI.

- [x] **Context consumption design doc** (item #12, bullet 3) — Expanded
  module docstring in `gchat/card_builder/context.py` documenting why
  sequential ordering was chosen and why "smarter" alternatives are wrong.

### Correction: The Wrapper Has Two Consumers

Item #6 speculated that the wrapper *could* wrap any Python module.
It already does:

```
   ModuleWrapper
   ├── card_framework.v2        (gchat/card_framework_wrapper.py)
   │   52 components, symbol DSL, DAG, context consumption
   │
   └── qdrant_client.models     (middleware/qdrant_core/qdrant_models_wrapper.py)
       Pydantic models, filter DSL, symbol generation
```

`qdrant_models_wrapper.py` follows the same singleton pattern, generates
its own symbol table, and powers the Qdrant filter DSL notation
(e.g., `ƒ{must=[ʄ{key="tool_name", match=☆{value="search"}}]}`).
Same infrastructure, completely different domain.

This means:
- The generic design has **already paid for itself**
- Card-specific logic correctly lives in `wrapper_setup.py` / `wrapper_api.py`,
  not in `module_wrapper/` — and this boundary must stay clean
- The 42k line count includes infrastructure serving two domains, not one.
  A fairer complexity comparison would be SQLAlchemy (~70k lines), which
  also does introspection + query building + caching + relationship mapping
  over a domain model it doesn't own

### All Action Items — Closed

All retrospective action items are resolved. Summary:

| # | Item | Status | Resolution |
|---|------|--------|------------|
| 9 | Wrapper seam split | Done | 106-line facade + 3 implementation files |
| 10 | CARD_BUILDER_STRICT | Done | 7 instrumentation sites, `strict.py` module |
| 11 | Onboarding walkthrough | Done | v2 build trace added below |
| 12.1 | Symbol lint | Done | `lint_no_hardcoded_symbols.py` in CI |
| 12.2 | DAG-bypass lint | Done | `lint_no_dag_bypass.py` (DSL002, WARNING) in CI |
| 12.3 | Context consumption docs | Done | Design rationale in `context.py` docstring |
| 10+ | Extend STRICT later | Deferred | Low-level cache miss paths are normal, not bugs |

---

## Appendix: v2 Build Trace (Onboarding Reference)

*This annotated trace replaces the v1 mermaid diagrams. Follow it to
understand how one card is built from DSL input to Google Chat JSON —
including where Qdrant is involved at every stage.*

```
send_dynamic_card("§[δ, Ƀ[ᵬ×2]]", card_params={δ: {text: "Hi"}, ᵬ: [{text: "Yes"}, {text: "No"}]})
│
│ ╔══════════════════════════════════════════════════════════════╗
│ ║  BEFORE BUILD — Qdrant pattern reuse                       ║
│ ╚══════════════════════════════════════════════════════════════╝
│
├─ gchat/card_tools.py → card_params coercion (JSON string → dict), URL extraction
│  └─ If NO DSL in input:                        [card_tools.py:~800]
│     └─ wrapper.search_by_dsl(inputs vector, type="instance_pattern")
│        └─ Qdrant search: "have we built something like this before?"
│        └─ If match found → extract DSL from pattern's relationship_text
│        └─ Reuse as suggested_dsl (skip synthesis entirely)
│
│ ╔══════════════════════════════════════════════════════════════╗
│ ║  DURING BUILD — structure, context, Qdrant style lookup     ║
│ ╚══════════════════════════════════════════════════════════════╝
│
├─ SmartCardBuilderV2.build()                    [builder_v2.py:~380]
│  │
│  ├─ _query_wrapper_patterns()                  [builder_v2.py:~340]
│  │  └─ TWO parallel Qdrant searches (ThreadPoolExecutor):
│  │     ├─ search_hybrid(inputs + relationships vectors)
│  │     │  └─ ColBERT on inputs, MiniLM on relationships
│  │     │  └─ Filters: content_feedback="positive", form_feedback="positive"
│  │     │  └─ Returns: style_metadata (colors, jinja_filters, semantic_styles)
│  │     │
│  │     └─ search_by_dsl(inputs vector, type="instance_pattern")
│  │        └─ If DSL detected in description → find matching patterns
│  │
│  │  └─ Fallback: query_with_discovery()        [feedback_loop.py:~2159]
│  │     └─ THREE Qdrant queries:
│  │        ├─ Component class search (components vector, no feedback)
│  │        ├─ Content Discovery (inputs vector + feedback context pairs)
│  │        │  └─ Qdrant Discovery API: positive IDs attract, negative repel
│  │        └─ Form Discovery (relationships vector + feedback context pairs)
│  │
│  ├─ DSLParser.parse("§[δ, Ƀ[ᵬ×2]]")          [dsl_parser.py]
│  │  └─ symbols resolved from wrapper.symbol_mapping (not hardcoded)
│  │  └─ Structure tree: Section[DecoratedText, ButtonList[Button×2]]
│  │
│  ├─ Context initialization                     [builder_v2.py:~1039]
│  │  └─ {buttons: [{text:"Yes"}, {text:"No"}], content_texts: [{text:"Hi"}],
│  │      _button_index: 0, _text_index: 0}
│  │  └─ style_metadata from Qdrant merged into context (auto-styling)
│  │
│  ├─ _build_component("Section", children=[...]) [builder_v2.py]
│  │  ├─ _build_widget_generic("DecoratedText")   [builder_v2.py:~1189]
│  │  │  └─ consume_from_context("DecoratedText")  [context.py:14]
│  │  │     └─ content_texts[0] → {text: "Hi"}, _text_index → 1
│  │  │
│  │  └─ _build_container_generic("ButtonList")    [builder_v2.py:~1274]
│  │     ├─ _build_widget_generic("Button")        ×2
│  │     │  └─ consume_from_context("Button")       [context.py:14]
│  │     │     └─ buttons[0] → {text:"Yes"}, _button_index → 1
│  │     │     └─ buttons[1] → {text:"No"},  _button_index → 2
│  │     └─ build_button_via_wrapper()              [rendering.py:321]
│  │        └─ wrapper.get_cached_class("OnClick")  [cache_mixin.py:303]
│  │
│  ├─ card_framework Section(...).render() → snake_case JSON
│  └─ convert_to_camel_case() → Google Chat API format  [rendering.py:80]
│
│ ╔══════════════════════════════════════════════════════════════╗
│ ║  AFTER BUILD — Qdrant pattern storage (learning loop)       ║
│ ╚══════════════════════════════════════════════════════════════╝
│
├─ feedback_loop.store_instance_pattern()        [builder_v2.py:~2417]
│  └─ Stores TWO Qdrant points:
│     ├─ Content pattern (type="content")
│     │  └─ 3 vectors: components (ColBERT), inputs (description),
│     │     relationships (MiniLM structure embedding)
│     │  └─ Payload: instance_params, relationship_text (DSL for reuse),
│     │     card_description, content_feedback, form_feedback
│     │
│     └─ Feedback UI pattern (type="feedback_ui")
│        └─ Same vectors, tagged separately for feedback button cards
│
│  └─ Next call's BEFORE phase finds this pattern → closed loop
│
└─ Deliver via webhook or Chat API
```

### Reading the trace

**Phase 1 — BEFORE BUILD: Pattern Reuse** (`card_tools.py:~800`)

When `send_dynamic_card` receives a description with no DSL, it asks
Qdrant: "have we built something like this before?" It searches the
`inputs` vector for `instance_pattern` points — these are previously
successful cards stored after delivery. If a match is found, the DSL
is extracted from the pattern's `relationship_text` field and reused
directly, skipping DSL synthesis entirely. This is why the second time
you ask for "a status card with 3 items" it builds faster — the DSL
structure is already in Qdrant.

**Phase 2 — DURING BUILD: Style & Pattern Lookup** (`builder_v2.py:~340`)

Even when DSL is provided explicitly, the builder runs parallel Qdrant
searches to find **styling metadata** from similar past cards. Two
searches run in a ThreadPoolExecutor:

- **Hybrid search** (`search_hybrid`): queries both the `inputs`
  vector (ColBERT embeddings of card content) and `relationships` vector
  (MiniLM embeddings of card structure). Filters for positive feedback
  only. Returns `style_metadata`: colors, Jinja filters, semantic styles.
- **DSL search** (`search_by_dsl`): if DSL is detected in the description,
  searches for matching instance patterns on the `inputs` vector.

If both searches miss, a fallback uses Qdrant's **Discovery API**
(`feedback_loop.py:~2159`) which runs three queries: component class
search, content discovery with feedback context pairs (positive IDs
attract results, negative IDs repel), and form discovery on the
relationships vector.

The extracted style_metadata is merged into the build context so
widgets auto-inherit colors and formatting from similar successful cards.

**Phase 3 — Parsing** (`dsl_parser.py`)

`DSLParser.parse()` tokenizes the DSL string using symbols from
`wrapper.symbol_mapping` — never hardcoded. The parser resolves
`§` → Section, `δ` → DecoratedText, `Ƀ` → ButtonList, `ᵬ` → Button,
and `×2` → repeat count. Output is a structure tree.

**Phase 4 — Context Initialization** (`builder_v2.py:~1039`)

card_params are distributed into context pools: `δ` content →
`content_texts[]`, `ᵬ` content → `buttons[]`. Each pool gets an index
counter starting at 0. Style metadata from Phase 2's Qdrant searches
is merged into the context.

**Phase 5 — Recursive Build** (`builder_v2.py`)

`_build_component()` walks the structure tree. Leaf widgets call
`consume_from_context()` which pops the next item from the appropriate
pool (sequential — first button to first Button widget, etc.). Container
widgets call `_build_container_generic()` which recurses into children.

**Phase 6 — Rendering** (`rendering.py`)

Each component instantiates a `card_framework` class via
`wrapper.get_cached_class()`, calls `.render()` to get snake_case JSON,
then `convert_to_camel_case()` transforms to Google Chat API format
(e.g., `button_list` → `buttonList`).

**Phase 7 — AFTER BUILD: Pattern Storage** (`builder_v2.py:~2417`)

After successful delivery, the builder stores **two** instance pattern
points back to Qdrant via `feedback_loop.store_instance_pattern()`:

1. **Content pattern**: the main card, stored with 3 vectors
   (components/ColBERT, inputs/description, relationships/MiniLM) and
   payload including `relationship_text` (the DSL notation for future
   reuse), `instance_params`, and feedback scores.
2. **Feedback UI pattern**: the feedback button section, tagged separately.

This closes the loop: the next call's BEFORE phase (Phase 1) will find
this stored pattern via vector search.

### The three Qdrant vectors

| Vector | Embedding | Indexes | Used For |
|--------|-----------|---------|----------|
| `inputs` | ColBERT (token-level) | Card content, param values | Content similarity search, DSL reuse |
| `relationships` | MiniLM (sentence-level) | Card structure, component hierarchy | Structural similarity, form discovery |
| `components` | ColBERT (token-level) | Component class identity | Class resolution (non-feedback) |

### The feedback loop

```
  Build card → Deliver → User sees card
       ↑                       │
       │                       ▼
  Qdrant biases          Feedback button
  future searches ←──── 👍 positive / 👎 negative
  toward this pattern      updates content_feedback
                           and form_feedback scores
```

This is human-in-the-loop reinforcement learning without any ML
framework. Positive feedback biases future Discovery API searches
toward that pattern. Negative feedback repels. Over time, the system
converges on structures users actually want.
