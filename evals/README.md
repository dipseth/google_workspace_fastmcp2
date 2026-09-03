# Cross-Model Evals for Dynamic Tools

Evaluates the DSL-driven dynamic tools (`send_dynamic_card`, `compose_dynamic_email`,
module-wrapper search) across different sampling models, logging every run as a
**Langfuse dataset run** with per-item scores.

## How it works

- For each model in [models.json](models.json), a FastMCP client connects to the
  running server and names the model under test on every request via the
  `X-Sampling-Model` / `X-Sampling-Api-Base` / `X-Sampling-Api-Key` headers.
  FastMCP 4 has no client-fulfilled sampling: every sampling call a tool makes
  runs in the server's own runtime (`middleware/sampling_runtime.py`), routed to
  the named model — the model is still the only variable between runs.
- The server must be started with `SAMPLING_ALLOW_HEADER_OVERRIDE=true` for the
  headers to be honored (off by default); without it every run uses the server's
  default provider.
- Tools are called **directly** even in Code Mode (they're only hidden from
  `list_tools`), which avoids the 30s `execute` sandbox limit. If a direct call
  reports unknown-tool, the runner falls back to `execute`.
- Sampling tokens/latency/cost now accrue in the **server** process (Langfuse
  generations, `middleware/payment/cost_tracker.py`); the in-process LiteLLM
  `CustomLogger` only sees this process's own calls (the quality judge)
  to the active item (items run sequentially, `max_concurrency=1`).
- Each (model, scenario) becomes a Langfuse experiment item with scores:
  `success`, `latency_s`, `sampling_calls`, `prompt_tokens`, `completion_tokens`,
  `cost_usd`, and LLM-judged `quality` (0–1, with rationale as the comment).

## Which scenarios exercise sampling

| Scenario | Sampling path |
|---|---|
| `card-status-simple` | none — deterministic DSL baseline |
| `card-dsl-recovery` | broken DSL → sampling-based recovery |
| `card-draft-variations` | tool-equipped draft-variations agent (heaviest) |
| `email-weekly-status` | email pre-validation agent (always samples) |
| `module-search-buttons` | none — wrapped-component semantic search (optional) |

Note: the `send_dynamic_card` validation agent is registered with `enabled=False`
in `middleware/server_middleware_setup.py`, so valid-DSL card sends are fully
deterministic — identical across models by design.

## Running

Server must be running (`https://localhost:8002/mcp`). Auth uses
`EVAL_MCP_API_KEY` → `MCP_API_KEY` → `TEST_MCP_API_KEY` (first non-empty; the
TEST key was stale as of 2026-08-07).

```bash
uv run python -m evals.run_evals                        # all models × all items
uv run python -m evals.run_evals --models venice-glm-4.6
uv run python -m evals.run_evals --items email-weekly-status --no-judge
uv run python -m evals.run_evals --run-prefix nightly
```

Results land in:
- **Langfuse** → Datasets → `dynamic-tools-v1` → Runs (one run per model per
  invocation, named `<prefix>-<label>-<timestamp>`); compare runs side by side.
- `evals/results/run-<timestamp>.json` + a console summary table.

## Configuration

- **Models** ([models.json](models.json)): each entry is a LiteLLM model ref +
  key env + optional `api_base` and `pricing` (`input_per_mtok`/`output_per_mtok`,
  used when LiteLLM's cost map doesn't know the model — e.g. all Venice models).
  Everything currently routes through Venice's OpenAI-compatible endpoint,
  including Claude models. Direct Anthropic (`anthropic/<model>`) works once a
  valid `ANTHROPIC_API_KEY` is set.
- **Judge**: `judge` entry in models.json (Claude Sonnet via Venice). Judge calls
  are tagged `eval_judge` in Langfuse.
- **Scenarios** ([datasets/dynamic_tools.json](datasets/dynamic_tools.json)):
  synced to the Langfuse dataset on every run (upsert by stable item id).
  Removing an item locally leaves it in Langfuse but it won't be run.

## Caveats

- Real side effects: cards go to `MCP_CHAT_WEBHOOK`; emails are Gmail **drafts**
  (`action: "draft"`). `card-draft-variations` posts 3 cards per model per run.
- Sampling spend from evals is tracked by the server's cost tracker like any
  other usage and counts toward `SAMPLING_MONTHLY_BUDGET_USD`.
- Server-side traces (tool/phase spans) and eval-process traces (experiment
  items, generations, judge) are separate Langfuse traces; the dataset run is
  the joining view.
