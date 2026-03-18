"""FastEmbed-based Qdrant semantic cache for sampling responses.

Subclasses LiteLLM's QdrantSemanticCache to replace litellm.embedding()
with FastEmbed, avoiding an external embedding API dependency. Uses the
same sentence-transformers/all-MiniLM-L6-v2 model (384 dims) already
loaded elsewhere in the project.
"""

import asyncio
import logging
from typing import Any

from litellm._logging import print_verbose
from litellm.caching.qdrant_semantic_cache import QdrantSemanticCache

logger = logging.getLogger(__name__)


class FastEmbedQdrantCache(QdrantSemanticCache):
    """Qdrant semantic cache using FastEmbed instead of litellm.embedding().

    Avoids needing an external embedding API key (OpenAI/etc) by using the
    same FastEmbed model the rest of the project uses.
    """

    def __init__(
        self,
        fastembed_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        **kwargs,
    ):
        from fastembed import TextEmbedding

        self._fastembed = TextEmbedding(model_name=fastembed_model_name)
        # MiniLM-L6-v2 = 384 dims; parent defaults to 1536 (ada-002)
        kwargs.setdefault("vector_size", 384)
        kwargs.setdefault("embedding_model", "fastembed-local")  # placeholder, unused
        super().__init__(**kwargs)

    def _embed(self, text: str) -> list[float]:
        """Embed a single text string using FastEmbed (sync)."""
        return list(self._fastembed.embed([text]))[0].tolist()

    # ── Override the 4 methods that call litellm.embedding/aembedding ────

    def set_cache(self, key, value, **kwargs):
        print_verbose(f"fastembed qdrant semantic-cache set_cache, kwargs: {kwargs}")
        from litellm._uuid import uuid

        messages = kwargs["messages"]
        prompt = "".join(message["content"] for message in messages)

        embedding = self._embed(prompt)

        value = str(value)

        data = {
            "points": [
                {
                    "id": str(uuid.uuid4()),
                    "vector": embedding,
                    "payload": {
                        "text": prompt,
                        "response": value,
                    },
                },
            ]
        }
        self.sync_client.put(
            url=f"{self.qdrant_api_base}/collections/{self.collection_name}/points",
            headers=self.headers,
            json=data,
        )

    def get_cache(self, key, **kwargs):
        print_verbose(
            f"fastembed sync qdrant semantic-cache get_cache, kwargs: {kwargs}"
        )

        messages = kwargs["messages"]
        prompt = "".join(message["content"] for message in messages)

        embedding = self._embed(prompt)

        data = {
            "vector": embedding,
            "params": {
                "quantization": {
                    "ignore": False,
                    "rescore": True,
                    "oversampling": 3.0,
                }
            },
            "limit": 1,
            "with_payload": True,
        }

        search_response = self.sync_client.post(
            url=f"{self.qdrant_api_base}/collections/{self.collection_name}/points/search",
            headers=self.headers,
            json=data,
        )
        results = search_response.json()["result"]

        if results is None or (isinstance(results, list) and len(results) == 0):
            return None

        similarity = results[0]["score"]
        cached_prompt = results[0]["payload"]["text"]

        print_verbose(
            f"semantic cache: similarity threshold: {self.similarity_threshold}, "
            f"similarity: {similarity}, prompt: {prompt}, "
            f"closest_cached_prompt: {cached_prompt}"
        )
        if similarity >= self.similarity_threshold:
            cached_value = results[0]["payload"]["response"]
            print_verbose(
                f"got a cache hit, similarity: {similarity}, "
                f"Current prompt: {prompt}, cached_prompt: {cached_prompt}"
            )
            return self._get_cache_logic(cached_response=cached_value)
        return None

    async def async_set_cache(self, key, value, **kwargs):
        from litellm._uuid import uuid

        print_verbose(
            f"fastembed async qdrant semantic-cache set_cache, kwargs: {kwargs}"
        )

        messages = kwargs["messages"]
        prompt = "".join(message["content"] for message in messages)

        # FastEmbed .embed() is sync but fast (~1-2ms for single input)
        embedding = await asyncio.to_thread(self._embed, prompt)

        value = str(value)

        data = {
            "points": [
                {
                    "id": str(uuid.uuid4()),
                    "vector": embedding,
                    "payload": {
                        "text": prompt,
                        "response": value,
                    },
                },
            ]
        }

        await self.async_client.put(
            url=f"{self.qdrant_api_base}/collections/{self.collection_name}/points",
            headers=self.headers,
            json=data,
        )

    async def async_get_cache(self, key, **kwargs):
        print_verbose(
            f"fastembed async qdrant semantic-cache get_cache, kwargs: {kwargs}"
        )

        messages = kwargs["messages"]
        prompt = "".join(message["content"] for message in messages)

        embedding = await asyncio.to_thread(self._embed, prompt)

        data = {
            "vector": embedding,
            "params": {
                "quantization": {
                    "ignore": False,
                    "rescore": True,
                    "oversampling": 3.0,
                }
            },
            "limit": 1,
            "with_payload": True,
        }

        search_response = await self.async_client.post(
            url=f"{self.qdrant_api_base}/collections/{self.collection_name}/points/search",
            headers=self.headers,
            json=data,
        )

        results = search_response.json()["result"]

        if results is None:
            kwargs.setdefault("metadata", {})["semantic-similarity"] = 0.0
            return None
        if isinstance(results, list) and len(results) == 0:
            kwargs.setdefault("metadata", {})["semantic-similarity"] = 0.0
            return None

        similarity = results[0]["score"]
        cached_prompt = results[0]["payload"]["text"]

        print_verbose(
            f"semantic cache: similarity threshold: {self.similarity_threshold}, "
            f"similarity: {similarity}, prompt: {prompt}, "
            f"closest_cached_prompt: {cached_prompt}"
        )

        kwargs.setdefault("metadata", {})["semantic-similarity"] = similarity

        if similarity >= self.similarity_threshold:
            cached_value = results[0]["payload"]["response"]
            print_verbose(
                f"got a cache hit, similarity: {similarity}, "
                f"Current prompt: {prompt}, cached_prompt: {cached_prompt}"
            )
            return self._get_cache_logic(cached_response=cached_value)
        return None


def initialize_sampling_cache() -> bool:
    """Lazily initialize the FastEmbed Qdrant semantic cache for sampling.

    Sets litellm.cache if SAMPLING_CACHE_ENABLED is true. Safe to call
    multiple times — returns True if cache is active, False otherwise.
    """
    import litellm

    if litellm.cache is not None:
        return True

    try:
        from config.settings import settings

        if not settings.sampling_cache_enabled:
            return False

        cache = FastEmbedQdrantCache(
            fastembed_model_name=settings.sampling_cache_fastembed_model,
            qdrant_api_base=settings.qdrant_url,
            qdrant_api_key=settings.qdrant_api_key,
            collection_name=settings.sampling_cache_collection,
            similarity_threshold=settings.sampling_cache_similarity_threshold,
        )

        # Use type="local" to get a lightweight Cache wrapper that registers
        # the "cache" marker in litellm callbacks (required for acompletion
        # to call get_cache/set_cache). Then swap the backend to our
        # FastEmbed-backed QdrantSemanticCache.
        litellm.cache = litellm.Cache(type="local")
        litellm.cache.cache = cache

        logger.info(
            "Sampling semantic cache initialized: collection=%s, threshold=%.2f",
            settings.sampling_cache_collection,
            settings.sampling_cache_similarity_threshold,
        )
        return True

    except Exception as e:
        logger.warning("Failed to initialize sampling cache (non-fatal): %s", e)
        return False
