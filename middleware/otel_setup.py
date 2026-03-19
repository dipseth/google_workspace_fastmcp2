"""OpenTelemetry TracerProvider setup for Langfuse OTLP export.

Configures a global TracerProvider that exports spans to Langfuse's OTLP HTTP
endpoint.  This activates FastMCP's native ``tools/call`` spans and enables
custom parent-child span hierarchies for sampling phases.

LiteLLM's ``langfuse_otel`` callback creates its own isolated TracerProvider,
so LLM generation spans are linked to our traces via ``trace_id`` metadata
rather than true OTEL parent-child (a LiteLLM limitation).

Idempotent — safe to call multiple times.  No-op when Langfuse is not configured.
"""

from __future__ import annotations

import base64
import logging
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

logger = logging.getLogger(__name__)

_provider: Optional[TracerProvider] = None
_tracer: Optional[trace.Tracer] = None

SERVICE_NAME = "google-workspace-mcp"
TRACER_NAME = "mcp.sampling"


def configure_otel_for_langfuse() -> bool:
    """Create and register a global TracerProvider exporting to Langfuse OTLP.

    Reads Langfuse host / keys from settings.  The OTLP endpoint is
    ``{langfuse_host}/api/public/otel/v1/traces`` with Basic auth
    (``public_key:secret_key``).

    Returns:
        True if the provider was configured (or already configured),
        False if Langfuse is not enabled or setup failed.
    """
    global _provider, _tracer

    if _provider is not None:
        return True  # already configured

    try:
        from config.settings import settings

        if not settings.langfuse_enabled:
            logger.debug("OTEL setup skipped — Langfuse not configured")
            return False

        host = settings.langfuse_host.rstrip("/")
        public_key = settings.langfuse_public_key
        secret_key = settings.langfuse_secret_key

        if not all([host, public_key, secret_key]):
            logger.debug("OTEL setup skipped — incomplete Langfuse credentials")
            return False

        # Langfuse OTLP endpoint with Basic auth
        endpoint = f"{host}/api/public/otel/v1/traces"
        credentials = base64.b64encode(
            f"{public_key}:{secret_key}".encode()
        ).decode()
        headers = {"Authorization": f"Basic {credentials}"}

        exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)
        processor = BatchSpanProcessor(exporter)

        resource = Resource.create({"service.name": SERVICE_NAME})
        _provider = TracerProvider(resource=resource)
        _provider.add_span_processor(processor)

        trace.set_tracer_provider(_provider)
        _tracer = _provider.get_tracer(TRACER_NAME)

        logger.info("OTEL TracerProvider configured for Langfuse (endpoint=%s)", endpoint)
        return True

    except Exception as e:
        logger.warning("Failed to configure OTEL TracerProvider: %s", e)
        return False


def get_mcp_tracer() -> trace.Tracer:
    """Return the MCP tracer, creating a no-op tracer if not configured."""
    global _tracer
    if _tracer is not None:
        return _tracer
    return trace.get_tracer(TRACER_NAME)


def shutdown_otel() -> None:
    """Flush pending spans and shut down the TracerProvider."""
    global _provider, _tracer
    if _provider is not None:
        try:
            _provider.force_flush(timeout_millis=5000)
            _provider.shutdown()
            logger.info("OTEL TracerProvider shut down")
        except Exception as e:
            logger.warning("OTEL shutdown error: %s", e)
        finally:
            _provider = None
            _tracer = None
