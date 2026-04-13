"""
Model Artifact Management — cloud download + local cache with py-key-value-aio registry.

Leverages FastMCP's storage backend pattern (py-key-value-aio) for the metadata
registry, with pluggable blob transport for the actual binary downloads.

Architecture:
  - Registry (py-key-value-aio store): tracks artifact metadata (URI, hash, local path)
  - Transport (pluggable): downloads binary .pt files from cloud (GCS, S3, Azure, HTTP)
  - Cache: local filesystem directory for downloaded artifacts

Usage:
    provider = await ModelArtifactProvider.create(settings)
    local_path = await provider.ensure_artifact("gchat", "gs://bucket/model.pt")
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, runtime_checkable
from urllib.parse import urlparse

from config.enhanced_logging import setup_logger

logger = setup_logger()


# ---------------------------------------------------------------------------
# Blob Transport Protocol — one method: download bytes to a local path
# ---------------------------------------------------------------------------


@runtime_checkable
class BlobTransport(Protocol):
    """Protocol for downloading binary artifacts from cloud storage."""

    async def download(self, uri: str, dest: Path) -> None:
        """Download artifact at *uri* to local *dest* path."""
        ...

    def supports(self, scheme: str) -> bool:
        """Return True if this transport handles the given URI scheme."""
        ...


# ---------------------------------------------------------------------------
# Transport implementations
# ---------------------------------------------------------------------------


class HTTPTransport:
    """Download artifacts via HTTP/HTTPS."""

    def supports(self, scheme: str) -> bool:
        return scheme in ("http", "https")

    async def download(self, uri: str, dest: Path) -> None:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(uri) as resp:
                resp.raise_for_status()
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(".tmp")
                try:
                    with open(tmp, "wb") as f:
                        async for chunk in resp.content.iter_chunked(64 * 1024):
                            f.write(chunk)
                    tmp.rename(dest)
                except BaseException:
                    tmp.unlink(missing_ok=True)
                    raise


class GCSTransport:
    """Download artifacts from Google Cloud Storage (gs:// URIs).

    Requires ``google-cloud-storage`` package.  Falls back to ``gsutil``
    CLI if the library is unavailable.
    """

    def supports(self, scheme: str) -> bool:
        return scheme == "gs"

    async def download(self, uri: str, dest: Path) -> None:
        parsed = urlparse(uri)
        bucket_name = parsed.netloc
        blob_path = parsed.path.lstrip("/")

        dest.parent.mkdir(parents=True, exist_ok=True)

        # Try google-cloud-storage library first
        try:
            from google.cloud import storage as gcs_storage

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                self._download_with_library,
                gcs_storage,
                bucket_name,
                blob_path,
                dest,
            )
            return
        except ImportError:
            logger.debug(
                "google-cloud-storage not installed, falling back to gsutil CLI"
            )

        # Fallback: gsutil CLI
        proc = await asyncio.create_subprocess_exec(
            "gsutil", "cp", uri, str(dest),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"gsutil cp failed (rc={proc.returncode}): {stderr.decode()}"
            )

    @staticmethod
    def _download_with_library(
        gcs_storage: Any, bucket_name: str, blob_path: str, dest: Path
    ) -> None:
        client = gcs_storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        tmp = dest.with_suffix(".tmp")
        try:
            blob.download_to_filename(str(tmp))
            tmp.rename(dest)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise


class S3Transport:
    """Download artifacts from AWS S3 (s3:// URIs).

    Requires ``boto3`` package.
    """

    def supports(self, scheme: str) -> bool:
        return scheme == "s3"

    async def download(self, uri: str, dest: Path) -> None:
        import boto3

        parsed = urlparse(uri)
        bucket_name = parsed.netloc
        key = parsed.path.lstrip("/")

        dest.parent.mkdir(parents=True, exist_ok=True)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._download_sync, bucket_name, key, dest
        )

    @staticmethod
    def _download_sync(bucket_name: str, key: str, dest: Path) -> None:
        import boto3

        s3 = boto3.client("s3")
        tmp = dest.with_suffix(".tmp")
        try:
            s3.download_file(bucket_name, key, str(tmp))
            tmp.rename(dest)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise


class AzureBlobTransport:
    """Download artifacts from Azure Blob Storage (az:// URIs).

    Requires ``azure-storage-blob`` package.
    URI format: az://container/path/to/blob
    """

    def supports(self, scheme: str) -> bool:
        return scheme == "az"

    async def download(self, uri: str, dest: Path) -> None:
        from azure.storage.blob.aio import BlobServiceClient

        parsed = urlparse(uri)
        container_name = parsed.netloc
        blob_path = parsed.path.lstrip("/")

        # Azure connection string from env
        conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
        if not conn_str:
            raise RuntimeError(
                "AZURE_STORAGE_CONNECTION_STRING required for az:// artifacts"
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        try:
            async with BlobServiceClient.from_connection_string(conn_str) as client:
                blob_client = client.get_blob_client(container_name, blob_path)
                with open(tmp, "wb") as f:
                    stream = await blob_client.download_blob()
                    async for chunk in stream.chunks():
                        f.write(chunk)
            tmp.rename(dest)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise


# ---------------------------------------------------------------------------
# Transport registry
# ---------------------------------------------------------------------------

_DEFAULT_TRANSPORTS: list[BlobTransport] = [
    HTTPTransport(),
    GCSTransport(),
    S3Transport(),
    AzureBlobTransport(),
]


def _get_transport(uri: str, transports: list[BlobTransport] | None = None) -> BlobTransport:
    """Resolve the transport for a given URI scheme."""
    scheme = urlparse(uri).scheme.lower()
    for t in (transports or _DEFAULT_TRANSPORTS):
        if t.supports(scheme):
            return t
    raise ValueError(
        f"No transport for URI scheme '{scheme}' (uri={uri}). "
        f"Supported: gs://, s3://, az://, http://, https://"
    )


# ---------------------------------------------------------------------------
# Registry — py-key-value-aio backed metadata store
# ---------------------------------------------------------------------------


async def _create_registry_store(backend: str, cache_dir: Path) -> Any:
    """Create a py-key-value-aio store for artifact metadata.

    Uses the same storage backend pattern as FastMCP (MemoryStore,
    FileTreeStore, RedisStore).

    Args:
        backend: 'memory', 'file', or 'redis'
        cache_dir: local cache directory (used by file backend)

    Returns:
        A py-key-value-aio store instance
    """
    if backend == "memory":
        from key_value.aio.stores.memory import MemoryStore
        store = MemoryStore()
        await store.setup()
        return store

    if backend == "file":
        from key_value.aio.stores.filetree import (
            FileTreeStore,
            FileTreeV1CollectionSanitizationStrategy,
            FileTreeV1KeySanitizationStrategy,
        )
        registry_dir = cache_dir / ".registry"
        registry_dir.mkdir(parents=True, exist_ok=True)
        store = FileTreeStore(
            data_directory=registry_dir,
            key_sanitization_strategy=FileTreeV1KeySanitizationStrategy(registry_dir),
            collection_sanitization_strategy=FileTreeV1CollectionSanitizationStrategy(
                registry_dir
            ),
        )
        await store.setup()
        return store

    if backend == "redis":
        from key_value.aio.stores.redis import RedisStore
        redis_url = os.environ.get("REDIS_IO_URL_STRING", "")
        if not redis_url:
            logger.warning(
                "MODEL_ARTIFACT_REGISTRY_BACKEND=redis but REDIS_IO_URL_STRING not set, "
                "falling back to file backend"
            )
            return await _create_registry_store("file", cache_dir)

        # Parse redis URL for host/port/password
        parsed = urlparse(redis_url)
        store = RedisStore(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            password=parsed.password or None,
        )
        await store.setup()
        return store

    raise ValueError(f"Unknown registry backend: {backend!r} (use 'memory', 'file', or 'redis')")


# ---------------------------------------------------------------------------
# ModelArtifactProvider — main interface
# ---------------------------------------------------------------------------

_COLLECTION = "model_artifacts"


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(128 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class ModelArtifactProvider:
    """Downloads, caches, and tracks model artifacts with cloud storage support.

    The registry (py-key-value-aio) stores metadata per artifact:
        {domain}:{filename} -> {uri, sha256, local_path, size_bytes, downloaded_at}

    The blob transport handles the actual binary download from cloud providers.
    """

    def __init__(
        self,
        store: Any,
        cache_dir: Path,
        transports: list[BlobTransport] | None = None,
        verify_checksum: bool = True,
    ):
        self._store = store
        self._cache_dir = cache_dir
        self._transports = transports or _DEFAULT_TRANSPORTS
        self._verify_checksum = verify_checksum
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    async def create(cls, settings: Any) -> "ModelArtifactProvider":
        """Factory: create provider from Settings instance."""
        from config.settings import settings as _settings

        s = settings or _settings

        cache_dir = Path(s.model_artifact_cache_dir) if s.model_artifact_cache_dir else (
            Path(s.credentials_dir) / "model_cache"
        )

        store = await _create_registry_store(s.model_artifact_registry_backend, cache_dir)
        await store.setup_collection(collection=_COLLECTION)

        return cls(
            store=store,
            cache_dir=cache_dir,
            verify_checksum=s.model_artifact_checksum_verify,
        )

    def _local_path_for(self, domain: str, uri: str) -> Path:
        """Deterministic local path for a given domain + URI."""
        filename = Path(urlparse(uri).path).name
        return self._cache_dir / domain / filename

    async def get_registry_entry(self, domain: str, filename: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a cached artifact."""
        key = f"{domain}:{filename}"
        return await self._store.get(key, collection=_COLLECTION)

    async def _update_registry(
        self, domain: str, filename: str, uri: str, local_path: Path, sha256: str
    ) -> None:
        """Update registry with artifact metadata."""
        import datetime

        key = f"{domain}:{filename}"
        await self._store.put(
            key,
            {
                "uri": uri,
                "sha256": sha256,
                "local_path": str(local_path),
                "size_bytes": local_path.stat().st_size,
                "downloaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "domain": domain,
            },
            collection=_COLLECTION,
        )

        # Maintain a key index (FileTreeStore lacks keys() method)
        index = await self._store.get("__index__", collection=_COLLECTION) or {"keys": []}
        if key not in index["keys"]:
            index["keys"].append(key)
            await self._store.put("__index__", index, collection=_COLLECTION)

    async def ensure_artifact(self, domain: str, uri: str) -> Path:
        """Ensure an artifact is downloaded and cached locally.

        Returns the local filesystem path to the artifact. Downloads from
        the cloud URI if not already cached (or if checksum mismatch).

        Args:
            domain: Domain identifier (e.g., 'gchat', 'email')
            uri: Cloud storage URI (gs://, s3://, az://, https://)

        Returns:
            Path to the local cached artifact file
        """
        local_path = self._local_path_for(domain, uri)
        filename = local_path.name

        # Check registry for existing entry
        entry = await self.get_registry_entry(domain, filename)

        if entry and local_path.exists():
            # Verify checksum if enabled
            if self._verify_checksum and entry.get("sha256"):
                actual = _sha256_file(local_path)
                if actual == entry["sha256"]:
                    logger.debug(
                        f"Artifact cache hit: {domain}/{filename} (sha256 verified)"
                    )
                    return local_path
                else:
                    logger.warning(
                        f"Artifact checksum mismatch for {domain}/{filename}, "
                        f"re-downloading (expected={entry['sha256'][:12]}..., "
                        f"actual={actual[:12]}...)"
                    )
            else:
                logger.debug(f"Artifact cache hit: {domain}/{filename}")
                return local_path

        # Download from cloud
        transport = _get_transport(uri, self._transports)
        logger.info(
            f"Downloading model artifact: {uri} -> {local_path} "
            f"(transport={type(transport).__name__})"
        )

        local_path.parent.mkdir(parents=True, exist_ok=True)
        await transport.download(uri, local_path)

        # Compute checksum and update registry
        sha256 = _sha256_file(local_path)
        await self._update_registry(domain, filename, uri, local_path, sha256)

        size_kb = local_path.stat().st_size / 1024
        logger.info(
            f"Artifact downloaded: {domain}/{filename} "
            f"({size_kb:.1f} KB, sha256={sha256[:12]}...)"
        )
        return local_path

    async def ensure_all(self, uri_map: Dict[str, str]) -> Dict[str, Path]:
        """Download all artifacts in parallel.

        Args:
            uri_map: {domain: uri} mapping

        Returns:
            {domain: local_path} mapping
        """
        tasks = {
            domain: self.ensure_artifact(domain, uri)
            for domain, uri in uri_map.items()
        }
        results = {}
        for domain, coro in tasks.items():
            try:
                results[domain] = await coro
            except Exception as e:
                logger.error(f"Failed to download artifact for {domain}: {e}")
        return results

    async def list_cached(self) -> list[Dict[str, Any]]:
        """List all cached artifact metadata from registry."""
        index = await self._store.get("__index__", collection=_COLLECTION)
        if not index or not index.get("keys"):
            return []
        entries = await self._store.get_many(index["keys"], collection=_COLLECTION)
        return [e for e in entries if e is not None]

    async def invalidate(self, domain: str, filename: str) -> bool:
        """Remove an artifact from cache and registry."""
        key = f"{domain}:{filename}"
        entry = await self._store.get(key, collection=_COLLECTION)
        if entry and entry.get("local_path"):
            Path(entry["local_path"]).unlink(missing_ok=True)
        deleted = await self._store.delete(key, collection=_COLLECTION)

        # Update key index
        index = await self._store.get("__index__", collection=_COLLECTION) or {"keys": []}
        if key in index["keys"]:
            index["keys"].remove(key)
            await self._store.put("__index__", index, collection=_COLLECTION)

        return deleted


# ---------------------------------------------------------------------------
# Module-level helper for parsing MODEL_ARTIFACT_URI setting
# ---------------------------------------------------------------------------


def parse_artifact_uri_setting(value: str) -> Dict[str, str]:
    """Parse MODEL_ARTIFACT_URI into a {domain: uri} mapping.

    Accepts either:
      - JSON object: '{"gchat": "gs://bucket/model.pt", "email": "gs://bucket/email.pt"}'
      - Single URI: 'gs://bucket/model.pt' (applied to all domains as 'default')

    Returns:
        Dict mapping domain names to URIs
    """
    if not value or not value.strip():
        return {}

    value = value.strip()
    if value.startswith("{"):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            logger.warning(f"MODEL_ARTIFACT_URI is not valid JSON: {value[:100]}")
            return {}

    # Single URI — assign to 'default' domain
    return {"default": value}
