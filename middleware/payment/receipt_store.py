"""Fire-and-forget Qdrant storage for x402 payment receipts.

Stores HMAC-signed payment receipts in the ``RECEIPT_COLLECTION`` Qdrant
collection for audit, analytics, and billing reconciliation.  All writes
are background tasks — callers never block on Qdrant I/O.

Collection is lazily created on first write with a simple 384-dim vector
(same as the tool-response collection) plus payload indexes for common
query patterns (wallet, network, tool, timestamp).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()

# Module-level state
_collection_ready = False
_init_lock = asyncio.Lock()
_background_tasks: set[asyncio.Task] = set()


def _track_task(task: asyncio.Task) -> None:
    """Track a background task so it isn't garbage-collected."""
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _ensure_collection() -> bool:
    """Lazily create the receipt collection if it doesn't exist.

    Creates a single 384-dim vector (MiniLM-L6-v2 compatible) plus
    payload field indexes for efficient filtering.

    Returns True if the collection is ready, False on error.
    """
    global _collection_ready
    if _collection_ready:
        return True

    async with _init_lock:
        if _collection_ready:
            return True

        try:
            from config.qdrant_client import get_qdrant_client
            from config.settings import settings

            client = get_qdrant_client()
            if client is None:
                logger.debug("Qdrant client not available — receipt storage disabled")
                return False

            collection_name = settings.receipt_collection

            # Check if collection already exists
            try:
                existing = await asyncio.to_thread(client.get_collections)
                names = [c.name for c in existing.collections]
                if collection_name in names:
                    _collection_ready = True
                    logger.info(
                        "Receipt collection '%s' already exists", collection_name
                    )
                    return True
            except Exception:
                pass

            # Create collection with a single 384-dim vector
            from qdrant_client.models import Distance, VectorParams

            await asyncio.to_thread(
                client.create_collection,
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=384,
                    distance=Distance.COSINE,
                ),
            )

            # Create payload indexes for common query patterns
            from qdrant_client.models import PayloadSchemaType

            indexes = {
                "payer_wallet": PayloadSchemaType.KEYWORD,
                "recipient_wallet": PayloadSchemaType.KEYWORD,
                "network": PayloadSchemaType.KEYWORD,
                "tool_name": PayloadSchemaType.KEYWORD,
                "auth_provenance": PayloadSchemaType.KEYWORD,
                "timestamp_unix": PayloadSchemaType.INTEGER,
                "amount": PayloadSchemaType.FLOAT,
                "hmac": PayloadSchemaType.KEYWORD,
                "settlement_tx_hash": PayloadSchemaType.KEYWORD,
            }

            for field_name, schema_type in indexes.items():
                try:
                    await asyncio.to_thread(
                        client.create_payload_index,
                        collection_name=collection_name,
                        field_name=field_name,
                        field_schema=schema_type,
                    )
                except Exception:
                    pass  # Index may already exist

            _collection_ready = True
            logger.info(
                "Created receipt collection '%s' with %d payload indexes",
                collection_name,
                len(indexes),
            )
            return True

        except Exception as e:
            logger.warning("Failed to create receipt collection: %s", e)
            return False


async def _store_receipt_impl(receipt_dict: dict, embed_text: str) -> None:
    """Internal: generate embedding and upsert receipt to Qdrant."""
    try:
        from config.qdrant_client import get_qdrant_client
        from config.settings import settings

        ready = await _ensure_collection()
        if not ready:
            return

        client = get_qdrant_client()
        if client is None:
            return

        # Generate embedding from a searchable text representation
        from middleware.qdrant_core.client import get_or_create_client_manager

        cm = get_or_create_client_manager()
        if cm and cm.embedder:
            embedding_list = await asyncio.to_thread(
                lambda q: list(cm.embedder.embed([q])), embed_text
            )
            vector = embedding_list[0].tolist() if embedding_list else [0.0] * 384
        else:
            vector = [0.0] * 384  # Zero vector if embedder unavailable

        from qdrant_client.models import PointStruct

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=receipt_dict,
        )

        await asyncio.to_thread(
            client.upsert,
            collection_name=settings.receipt_collection,
            points=[point],
        )

        logger.debug(
            "Receipt stored in Qdrant: payer=%s tool=%s amount=%s",
            receipt_dict.get("payer_wallet", "?")[:12],
            receipt_dict.get("tool_name", "?"),
            receipt_dict.get("amount", "?"),
        )

    except Exception as e:
        logger.warning("Failed to store receipt in Qdrant: %s", e)


def store_receipt_async(receipt_dict: dict) -> None:
    """Fire-and-forget: store a payment receipt in Qdrant.

    Call this from synchronous or async code — it creates a background
    task that never blocks the caller.

    Args:
        receipt_dict: Serialized PaymentReceipt (from receipt.model_dump()).
    """
    # Build a searchable text summary for embedding
    payer = receipt_dict.get("payer", {})
    parts = [
        f"payment receipt",
        f"tool:{receipt_dict.get('tool_name', '')}",
        f"amount:{receipt_dict.get('amount', '')} USDC",
        f"network:{receipt_dict.get('network', '')}",
        f"payer:{payer.get('wallet_address', '')}",
    ]
    if payer.get("user_email"):
        parts.append(f"user:{payer['user_email']}")
    embed_text = " ".join(parts)

    # Flatten the receipt for Qdrant payload (no nested dicts for indexing)
    flat = {
        "payer_wallet": payer.get("wallet_address", ""),
        "payer_email": payer.get("user_email", ""),
        "payer_google_sub": payer.get("google_sub", ""),
        "auth_provenance": payer.get("auth_provenance", ""),
        "tool_name": receipt_dict.get("tool_name", ""),
        "amount": receipt_dict.get("amount", ""),
        "network": receipt_dict.get("network", ""),
        "tx_hash": receipt_dict.get("tx_hash", ""),
        "settlement_tx_hash": receipt_dict.get("tx_hash", ""),
        "verified_at": receipt_dict.get("verified_at", 0),
        "timestamp_unix": int(receipt_dict.get("verified_at", 0)),
        "expires_at": receipt_dict.get("expires_at", 0),
        "resource_url": receipt_dict.get("resource_url", ""),
        "hmac": receipt_dict.get("hmac", ""),
        "receipt_version": 1,
    }

    # Determine recipient from resource_url or settings
    try:
        from config.settings import settings

        flat["recipient_wallet"] = settings.payment_recipient_wallet
    except Exception:
        pass

    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_store_receipt_impl(flat, embed_text))
        _track_task(task)
    except RuntimeError:
        # No running event loop — skip storage
        logger.debug("No event loop available for receipt storage")
