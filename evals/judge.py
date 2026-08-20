"""LLM-as-judge scoring for dynamic-tool eval outputs."""

from __future__ import annotations

import json
import re

JUDGE_SYSTEM = (
    "You are a strict evaluator of MCP tool executions. You are given the tool "
    "name, the exact arguments sent, the evaluation criteria, and the tool's "
    "response. Judge ONLY whether the response satisfies the criteria. "
    "Respond with a single JSON object: "
    '{"score": <float 0.0-1.0>, "rationale": "<one or two sentences>"}. '
    "Score 1.0 = fully satisfies criteria; 0.0 = failed or errored; partial "
    "credit for partially correct structure/content. No markdown, JSON only."
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


async def judge_quality(
    *,
    tool: str,
    args: dict,
    criteria: str,
    output_text: str,
    judge_model: str,
    api_key: str | None = None,
    api_base: str | None = None,
) -> dict:
    """Score one tool execution 0..1 against the scenario criteria.

    Returns ``{"score": float, "rationale": str}``; on judge failure returns
    score -1 so callers can skip logging it.
    """
    import litellm

    user_prompt = (
        f"Tool: {tool}\n\n"
        f"Arguments:\n{json.dumps(args, ensure_ascii=False, default=str)[:4000]}\n\n"
        f"Evaluation criteria:\n{criteria}\n\n"
        f"Tool response:\n{output_text[:6000]}"
    )
    try:
        extra: dict = {}
        if api_key:
            extra["api_key"] = api_key
        if api_base:
            extra["api_base"] = api_base
        resp = await litellm.acompletion(
            model=judge_model,
            **extra,
            # Judge prompts are near-identical across items — semantic caching
            # would replay one verdict everywhere. Never cache.
            cache={"no-cache": True, "no-store": True},
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=500,
            metadata={
                "generation_name": "eval_judge",
                "trace_name": "eval_judge",
                "tags": ["eval", "judge"],
            },
        )
        text = resp.choices[0].message.content or ""
        match = _JSON_RE.search(text)
        parsed = json.loads(match.group(0)) if match else {}
        score = float(parsed.get("score", -1))
        score = max(0.0, min(1.0, score)) if score >= 0 else -1.0
        return {"score": score, "rationale": str(parsed.get("rationale", ""))[:500]}
    except Exception as e:
        return {"score": -1.0, "rationale": f"judge error: {e}"}
