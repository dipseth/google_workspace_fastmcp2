"""Adhoc: mimic ModuleWrapper Qdrant query for card framework components.

This script:
- Loads `QDRANT_URL` + `QDRANT_KEY` from `.env` (if not already set).
- Embeds a natural-language query using `fastembed` (bge-small-en-v1.5).
- Calls Qdrant's `/collections/<collection>/points/query` endpoint directly (HTTP).

Why HTTP instead of `qdrant_client.query_points`?
- This repo currently uses a `qdrant_client` variant that routes through a
  `qdrant_fastembed` wrapper which rejects `QueryRequest` objects.
- Using raw HTTP reproduces the actual query the server performs.

Run:
- `SSL_CERT_FILE="$(uv run python -c 'import certifi; print(certifi.where())')" uv run python scripts/adhoc_qdrant_card_framework_query.py`

Optional env overrides:
- `QDRANT_COLLECTION` (default: card_framework_components_fastembed)
- `QDRANT_QUERY` (default: simple card with title and button)
- `QDRANT_LIMIT` (default: 5)

Note:
- The `SSL_CERT_FILE=...certifi...` export fixes macOS OpenSSL trust issues.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no external dependency)."""

    p = Path(path)
    if not p.exists():
        return

    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def main() -> int:
    load_dotenv(".env")

    qdrant_url = os.environ.get("QDRANT_URL")
    qdrant_key = os.environ.get("QDRANT_KEY")
    if not qdrant_url or not qdrant_key:
        raise SystemExit("Missing QDRANT_URL/QDRANT_KEY (set env or add to .env)")

    collection = os.environ.get("QDRANT_COLLECTION", "card_framework_components_fastembed")
    query_text = os.environ.get("QDRANT_QUERY", "simple card with title and button")
    limit = int(os.environ.get("QDRANT_LIMIT", "5"))

    from fastembed import TextEmbedding

    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    vector = [float(x) for x in next(model.embed([query_text]))]

    with httpx.Client(
        base_url=qdrant_url.rstrip("/"),
        headers={"api-key": qdrant_key},
        timeout=30.0,
    ) as client:
        resp = client.post(
            f"/collections/{collection}/points/query",
            json={
                "query": vector,
                "limit": limit,
                "with_payload": True,
                "with_vector": False,
            },
        )

    print("status:", resp.status_code)
    resp.raise_for_status()

    data = resp.json()
    points = (data.get("result") or {}).get("points") or []

    print("Collection:", collection)
    print("Query:", query_text)
    print("Top hits:")

    for i, p in enumerate(points, 1):
        payload = p.get("payload") or {}
        print(f"#{i} id={p.get('id')} score={p.get('score')}")

        # Show key identity fields (these are what we want to rely on in code)
        for k in [
            "name",
            "module_path",
            "full_path",
            "type",
            "title",
            "description",
            "module",
            "component",
        ]:
            if k in payload:
                s = str(payload[k])
                if len(s) > 200:
                    s = s[:200] + "…"
                print(f"  {k}: {s}")

        # If module_path+name exist, show the canonical path we will prefer
        module_path = payload.get("module_path")
        name = payload.get("name")
        if module_path and name:
            print(f"  canonical: {module_path}.{name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
