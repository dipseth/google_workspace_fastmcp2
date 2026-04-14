"""HTTP endpoint for serving attachment downloads via signed URLs.

Registered by ``setup_attachment_endpoints(mcp)`` in ``server.py``.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastmcp import FastMCP

from config.enhanced_logging import setup_logger

logger = setup_logger()


def setup_attachment_endpoints(mcp: FastMCP) -> None:
    """Register the ``/attachment-download`` HTTP endpoint."""

    @mcp.custom_route("/attachment-download", methods=["GET"])
    async def attachment_download(request: Any):
        """Serve a one-time attachment download via signed URL."""
        from starlette.responses import Response, StreamingResponse

        from gmail.attachment_server import (
            cleanup_attachment,
            get_attachment_path,
            verify_attachment_url,
        )

        query = dict(request.query_params)
        file_id = query.get("fid", "")
        filename = query.get("fn", "")
        exp = query.get("exp", "")
        sig = query.get("sig", "")

        if not all([file_id, filename, exp, sig]):
            return Response("Missing parameters", status_code=400)

        valid, fid, error = verify_attachment_url(file_id, filename, exp, sig)
        if not valid:
            if "Already downloaded" in error:
                return Response(error, status_code=410)
            if "expired" in error.lower():
                return Response(error, status_code=410)
            return Response(error, status_code=403)

        file_path = get_attachment_path(fid)
        if not file_path or not os.path.exists(file_path):
            return Response("File not found", status_code=404)

        # Sanitize filename for Content-Disposition
        safe_filename = os.path.basename(filename).replace('"', '\\"')

        async def file_stream():
            try:
                with open(file_path, "rb") as f:
                    while chunk := f.read(65536):
                        yield chunk
            finally:
                # Schedule cleanup after streaming completes
                asyncio.get_event_loop().call_soon(cleanup_attachment, fid)

        return StreamingResponse(
            file_stream(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_filename}"',
            },
        )
