"""Run cross-model evals of dynamic MCP tools, logged as Langfuse dataset runs.

For each model in evals/models.json a FastMCP client connects to the running
server, routing the server's sampling to that model per request, and executes every
dataset scenario (via code-mode `execute` when the server hides direct tools).
Each (model, scenario) pair becomes a Langfuse experiment/dataset-run item with
scores: success, latency, sampling calls, tokens, cost, and an LLM-judged
quality score.

Usage (server must be running):
    uv run python -m evals.run_evals                       # all models, all items
    uv run python -m evals.run_evals --models venice-glm-4.6
    uv run python -m evals.run_evals --items card-status-simple --no-judge
    uv run python -m evals.run_evals --run-prefix nightly
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

EVALS_DIR = Path(__file__).parent
RESULTS_DIR = EVALS_DIR / "results"

METRIC_KEYS = (
    "latency_s",
    "sampling_calls",
    "prompt_tokens",
    "completion_tokens",
    "cost_usd",
)


def _setup_env() -> None:
    load_dotenv()
    # .env uses LANGFUSE_BASE_URL; the Langfuse SDK reads LANGFUSE_HOST
    base = os.getenv("LANGFUSE_BASE_URL")
    if base and not os.getenv("LANGFUSE_HOST"):
        os.environ["LANGFUSE_HOST"] = base
    # .env sets SSL_CERT_FILE to the *server's* dev cert (for serving HTTPS).
    # In this client process that would be used as the CA bundle and break TLS
    # to Langfuse/providers — force certifi's real root bundle instead.
    try:
        import certifi

        os.environ["SSL_CERT_FILE"] = certifi.where()
        os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
    except ImportError:
        pass
    # The sampling handler lazily initializes the semantic response cache; in
    # the eval process that cross-contaminates similar prompts across models
    # and items (identical judge scores, replayed sampling responses). Kill it.
    os.environ["SAMPLING_CACHE_ENABLED"] = "false"


def _get_langfuse():
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        print("⚠️  Langfuse keys not set — running without Langfuse logging")
        return None
    try:
        from langfuse import get_client

        lf = get_client()
        if not lf.auth_check():
            print("⚠️  Langfuse auth_check failed — running without Langfuse logging")
            return None
        return lf
    except Exception as e:
        print(f"⚠️  Langfuse unavailable ({e}) — running without Langfuse logging")
        return None


def _sync_dataset(lf, spec: dict) -> None:
    """Create/refresh the Langfuse dataset from the local JSON spec."""
    name = spec["name"]
    lf.create_dataset(name=name, description=spec.get("description", ""))
    for item in spec["items"]:
        lf.create_dataset_item(
            dataset_name=name,
            id=f"{name}::{item['id']}",
            input={"tool": item["tool"], "args": item["args"]},
            metadata={
                "item_id": item["id"],
                "judge_criteria": item.get("judge_criteria", ""),
                "tags": item.get("tags", []),
                "optional": item.get("optional", False),
                "timeout_s": item.get("timeout_s", 240),
            },
        )


def _item_field(item, field: str, default=None):
    """Read a field from a DatasetItem object or a plain dict item."""
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)


def make_task(model_cfg: dict, collector, rows_sink: list):
    """Build the experiment task fn: run one scenario against the MCP server."""

    label = model_cfg["label"]

    async def task(*, item, **kwargs):
        from evals.harness import (
            make_client,
            result_to_text,
            summarize_usage,
        )

        inp = _item_field(item, "input") or {}
        meta = _item_field(item, "metadata") or {}
        tool, args = inp["tool"], inp["args"]
        item_id = meta.get("item_id", tool)
        call_timeout = meta.get("timeout_s") or 240

        ok, output_text, skipped = True, "", False
        latency_s = 0.0
        usage = summarize_usage({"calls": []})
        try:
            # One retry on connect — the server can be slow to accept a new
            # session while still finishing a previous long-running tool call.
            client = None
            for attempt in (1, 2):
                client = make_client(model_cfg)
                try:
                    await client.__aenter__()
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(10)
            try:
                available = {t.name for t in await client.list_tools()}
                collector.begin(item_id, label)
                t0 = time.perf_counter()
                try:
                    # Direct call works even in Code Mode (tools are only
                    # hidden from list_tools) and avoids the 30s sandbox limit.
                    result = await client.call_tool(tool, args, timeout=call_timeout)
                    output_text = result_to_text(result)
                except Exception as e1:
                    not_found = (
                        "unknown tool" in str(e1).lower()
                        or "not found" in str(e1).lower()
                    )
                    if not_found and "execute" in available:
                        try:
                            code = f"return await call_tool({tool!r}, {args!r})"
                            result = await client.call_tool(
                                "execute", {"code": code}, timeout=call_timeout
                            )
                            output_text = result_to_text(result)
                        except Exception as e2:
                            ok = False
                            output_text = f"ERROR: {e2}"
                    elif not_found:
                        skipped = True
                        ok = False
                        output_text = f"SKIPPED: tool '{tool}' not available on server"
                    else:
                        ok = False
                        output_text = f"ERROR: {e1}"
                latency_s = round(time.perf_counter() - t0, 3)
                usage = summarize_usage(collector.end())
            finally:
                await client.__aexit__(None, None, None)
        except Exception as e:
            ok = False
            output_text = f"ERROR: connection failed: {e}"

        # The tool doesn't exist server-side (execute sandbox says so) —
        # that's a skip, not a model failure.
        if "unknown tool" in output_text.lower():
            skipped = True
            ok = False

        # LiteLLM's cost map doesn't know Venice models — fall back to the
        # per-MTok pricing configured on the model entry, if any.
        pricing = model_cfg.get("pricing")
        if pricing and not usage["cost_usd"] and usage["total_tokens"]:
            usage["cost_usd"] = round(
                usage["prompt_tokens"] * pricing.get("input_per_mtok", 0) / 1e6
                + usage["completion_tokens"] * pricing.get("output_per_mtok", 0) / 1e6,
                6,
            )

        # Some tools report failure in the payload instead of raising
        head = output_text[:400].lower()
        if ok and (
            head.startswith("sandboxerror")
            or head.startswith("error")
            or '"success": false' in head
        ):
            ok = False

        row = {
            "model": label,
            "model_id": model_cfg["model"],
            "item": item_id,
            "status": "skipped" if skipped else ("ok" if ok else "error"),
            "latency_s": latency_s,
            **usage,
            "output_text": output_text,
        }
        rows_sink.append(row)
        icon = "⏭️ " if skipped else ("✅" if ok else "❌")
        print(
            f"   {icon} [{label}] {item_id}: {latency_s}s, "
            f"{usage['sampling_calls']} llm calls, {usage['total_tokens']} tok, "
            f"${usage['cost_usd']:.4f}"
        )
        return row

    return task


def metrics_evaluator(*, input, output, expected_output=None, metadata=None, **kwargs):
    """Turn the task's metric fields into Langfuse scores."""
    from langfuse import Evaluation

    if not isinstance(output, dict):
        return []
    if output.get("status") == "skipped":
        return []
    evals = [Evaluation(name="success", value=1 if output["status"] == "ok" else 0)]
    for key in METRIC_KEYS:
        evals.append(Evaluation(name=key, value=output.get(key, 0)))
    return evals


def make_judge_evaluator(judge_cfg: dict, rows_sink: list):
    async def judge_evaluator(
        *, input, output, expected_output=None, metadata=None, **kwargs
    ):
        from langfuse import Evaluation

        from evals.judge import judge_quality

        if not isinstance(output, dict) or output.get("status") != "ok":
            return []
        res = await judge_quality(
            tool=input["tool"] if isinstance(input, dict) else "",
            args=input.get("args", {}) if isinstance(input, dict) else {},
            criteria=(metadata or {}).get("judge_criteria", ""),
            output_text=output.get("output_text", ""),
            judge_model=judge_cfg["model"],
            api_key=os.getenv(judge_cfg.get("api_key_env", "")) or None,
            api_base=judge_cfg.get("api_base"),
        )
        if res["score"] < 0:
            print(f"      ⚖️  judge failed: {res['rationale'][:150]}")
            return []
        # Attach quality back onto the local row for the console summary
        for row in rows_sink:
            if row is output:
                row["quality"] = res["score"]
                row["quality_rationale"] = res["rationale"]
        print(f"      ⚖️  quality={res['score']:.2f} — {res['rationale'][:100]}")
        return [
            Evaluation(name="quality", value=res["score"], comment=res["rationale"])
        ]

    return judge_evaluator


def _print_summary(rows: list[dict]) -> None:
    by_model: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("status") in ("ok", "error"):
            by_model.setdefault(r["model"], []).append(r)
    if not by_model:
        return
    print("\n📊 Summary by model")
    header = f"{'model':<22}{'items':>6}{'ok':>4}{'avg s':>8}{'tokens':>9}{'cost $':>9}{'quality':>9}"
    print(header)
    print("-" * len(header))
    for label, rs in by_model.items():
        ok = [r for r in rs if r["status"] == "ok"]
        quals = [
            r["quality"]
            for r in rs
            if isinstance(r.get("quality"), (int, float)) and r["quality"] >= 0
        ]
        avg_latency = sum(r.get("latency_s", 0.0) for r in rs) / len(rs)
        tokens = sum(r.get("total_tokens", 0) for r in rs)
        cost = sum(r.get("cost_usd", 0.0) for r in rs)
        avg_q = f"{sum(quals) / len(quals):.2f}" if quals else "—"
        print(
            f"{label:<22}{len(rs):>6}{len(ok):>4}{avg_latency:>8.1f}{tokens:>9}{cost:>9.4f}{avg_q:>9}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", default=str(EVALS_DIR / "datasets" / "dynamic_tools.json")
    )
    parser.add_argument("--config", default=str(EVALS_DIR / "models.json"))
    parser.add_argument(
        "--models", nargs="*", help="model labels to run (default: all)"
    )
    parser.add_argument(
        "--items", nargs="*", help="dataset item ids to run (default: all)"
    )
    parser.add_argument("--run-prefix", default="dyn")
    parser.add_argument(
        "--no-judge", action="store_true", help="skip LLM-as-judge scoring"
    )
    args = parser.parse_args()

    _setup_env()

    spec = json.loads(Path(args.dataset).read_text())
    config = json.loads(Path(args.config).read_text())

    model_cfgs = config["models"]
    if args.models:
        model_cfgs = [m for m in model_cfgs if m["label"] in args.models]
        if not model_cfgs:
            raise SystemExit(f"No models matched {args.models}")
    missing_keys = [
        m["label"]
        for m in model_cfgs
        if m.get("api_key_env") and not os.getenv(m["api_key_env"])
    ]
    if missing_keys:
        print(f"⚠️  Skipping models with missing API keys: {missing_keys}")
        model_cfgs = [m for m in model_cfgs if m["label"] not in missing_keys]

    selected = spec["items"]
    if args.items:
        selected = [i for i in selected if i["id"] in args.items]
        if not selected:
            raise SystemExit(f"No dataset items matched {args.items}")
    selected_ids = {i["id"] for i in selected}

    judge_cfg = None if args.no_judge else config.get("judge")

    lf = _get_langfuse()
    lf_items = []
    if lf:
        _sync_dataset(lf, spec)
        dataset = lf.get_dataset(spec["name"])
        lf_items = [
            it
            for it in dataset.items
            if isinstance(it.metadata, dict)
            and it.metadata.get("item_id") in selected_ids
        ]

    from evals.harness import install_collector

    collector = install_collector()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    all_rows: list[dict] = []
    for model_cfg in model_cfgs:
        label = model_cfg["label"]
        run_name = f"{args.run_prefix}-{label}-{stamp}"
        print(f"\n🚀 Running {len(selected)} items on {label} ({model_cfg['model']})")

        rows_sink: list[dict] = []
        task = make_task(model_cfg, collector, rows_sink)
        evaluators = [metrics_evaluator]
        if judge_cfg:
            evaluators.append(make_judge_evaluator(judge_cfg, rows_sink))

        try:
            if lf:
                result = lf.run_experiment(
                    name=f"{args.run_prefix}-{label}",
                    run_name=run_name,
                    description=f"Dynamic-tool eval, sampling model {model_cfg['model']}",
                    data=lf_items,
                    task=task,
                    evaluators=evaluators,
                    max_concurrency=1,
                    metadata={"model": model_cfg["model"], "label": label},
                )
                url = getattr(result, "dataset_run_url", None) or getattr(
                    result, "run_url", None
                )
                if url:
                    print(f"   🔭 {url}")
            else:
                asyncio.run(_run_local_with_judge(selected, task, judge_cfg, rows_sink))
        except Exception as e:
            print(f"   ❌ [{label}] run failed: {e}")
            rows_sink.append(
                {"model": label, "item": "*", "status": "error", "note": str(e)}
            )
        all_rows.extend(rows_sink)

    if lf:
        lf.flush()

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / f"run-{stamp}.json"
    slim_rows = [
        {**r, "output_text": (r.get("output_text") or "")[:500]} for r in all_rows
    ]
    out_path.write_text(
        json.dumps({"stamp": stamp, "rows": slim_rows}, indent=2, ensure_ascii=False)
    )
    _print_summary(all_rows)
    print(f"\n💾 Results saved to {out_path}")
    if lf:
        print(
            f"🔭 Langfuse: dataset '{spec['name']}' → Runs tab "
            f"(host: {os.getenv('LANGFUSE_HOST')})"
        )


async def _run_local_with_judge(
    scenarios: list[dict], task, judge_cfg: dict | None, rows_sink: list
) -> None:
    from evals.judge import judge_quality

    for scenario in scenarios:
        row = await task(
            item={
                "input": {"tool": scenario["tool"], "args": scenario["args"]},
                "metadata": {
                    "item_id": scenario["id"],
                    "judge_criteria": scenario.get("judge_criteria", ""),
                    "optional": scenario.get("optional", False),
                    "timeout_s": scenario.get("timeout_s", 240),
                },
            }
        )
        if judge_cfg and row.get("status") == "ok":
            res = await judge_quality(
                tool=scenario["tool"],
                args=scenario["args"],
                criteria=scenario.get("judge_criteria", ""),
                output_text=row.get("output_text", ""),
                judge_model=judge_cfg["model"],
                api_key=os.getenv(judge_cfg.get("api_key_env", "")) or None,
                api_base=judge_cfg.get("api_base"),
            )
            if res["score"] >= 0:
                row["quality"] = res["score"]
                row["quality_rationale"] = res["rationale"]
                print(f"      ⚖️  quality={res['score']:.2f} — {res['rationale'][:100]}")


if __name__ == "__main__":
    main()
