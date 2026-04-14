# TRM / Diagnostic UI — Next Steps

**Date:** 2026-04-05
**Branch:** `reaserch_trm_mw`

## What's Done

- Both SearchEvalPanel and ModelComparisonPanel now display eval metadata: model type, wrapped domain (`card_framework.v2`), eval data file, feature version, candidate stats, and positive ratio
- Model comparison banner makes it explicit both models are scored on the same val split
- Backend endpoints (`/ml/search-evaluation`, `/ml/model-comparison`) return `eval_meta` with provenance info
- TypeScript types updated with `EvalMeta` interface and new fields on `ModelComparisonEntry`

## Current State of Models

| Model | Params | Accuracy | MRR | Trained On | Notes |
|-------|--------|----------|-----|------------|-------|
| DualHead MW | 5,618 | 3.1% | 20.9% | v5 (easy, ~12% pos ratio) | Evaluated on v5 val split — not trained for hard data |
| UnifiedTRN | 28,776 | 66.1% | 78.4% | v5_hard2 (713 groups, ~60% pos ratio) | Multi-task: form + content + pool + halt |

**Key issue:** The comparison is misleading — DualHead wasn't trained for the difficulty level it's being evaluated on.

## Short-Term (high impact, low effort)

1. **Embed `data_version` in training checkpoints**
   - Files: `research/trm/h2/train_unified.py`, `research/trm/h2/train_mw.py`
   - When saving checkpoints, include: `data_version` (filename), `git_commit`, `timestamp`
   - The UI already reads `data_version` from checkpoints — it just needs to be written

2. **Create a frozen eval set**
   - Currently eval = 20% of training data (seed=42 split)
   - Carve out ~50 groups into a separate file (e.g. `mw_eval_frozen.json`) that never appears in training
   - This makes metrics stable across retrains and data changes

3. **Fix the DualHead 3.1% discrepancy**
   - Option A: Retrain DualHead on v5_hard2 so comparison is apples-to-apples
   - Option B: Add a label in the UI: "DualHead not trained for this difficulty"
   - The UI now shows positive ratio — if it's yellow (>30%), that's a signal the model may not match the data

## Medium-Term (model quality)

4. **Retrain DualHead on v5_hard2**
   - Then the comparison panel becomes a true side-by-side on the same difficulty
   - Expected: DualHead accuracy should jump significantly once trained on matching data

5. **Wire real content vectors into UnifiedTRN eval**
   - `ml_eval.py` line ~2069 passes `content_zeros` to the unified model
   - Content score is always noise — wire in real 384D content embeddings from Qdrant
   - This would show the true combined (form + content) accuracy

6. **Expand training data to new domains**
   - Email (`email_framework`) and Qdrant (`qdrant_client.models`) wrappers are production but don't generate training data
   - Adding them validates "universal" module wrapping and gives the model more diversity

## Longer-Term (infrastructure)

7. **Metrics history tracking**
   - Store `(timestamp, model_name, data_version, metrics_dict)` tuples
   - Options: JSON file in `research/trm/h2/metrics_history.json`, SQLite, or Langfuse
   - Add a timeline chart to the diagnostic UI so you can see accuracy trends over retrains

8. **Langfuse experiment integration**
   - Wire eval runs into Langfuse experiments for automatic tracking
   - Compare prompt templates, model configs, and scoring approaches
   - Feed evaluation results back into fine-tuning decisions

## Key Files

| Area | File |
|------|------|
| SearchEvalPanel | `tools/diagnostic-ui/frontend/src/components/ml/SearchEvalPanel.tsx` |
| ModelComparisonPanel | `tools/diagnostic-ui/frontend/src/components/ml/ModelComparisonPanel.tsx` |
| Types | `tools/diagnostic-ui/frontend/src/types.ts` |
| Backend eval endpoints | `tools/diagnostic-ui/backend/routes/ml_eval.py` |
| DualHead training | `research/trm/h2/train_mw.py` |
| UnifiedTRN training | `research/trm/h2/train_unified.py` |
| Eval metrics | `research/trm/h2/eval_metrics.py` |
| Training data | `research/trm/h2/mw_synthetic_groups_v5.json` |
| Production slot assignment | `gchat/card_builder/slot_assignment.py` |
