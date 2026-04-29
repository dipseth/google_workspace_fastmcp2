"""HTTP endpoint for receiving client→server file uploads via signed URLs.

Inverse of ``/attachment-download``. Registered by
``setup_drive_upload_endpoints(mcp)`` in ``server.py``. Active when
``settings.drive_upload_client_fs`` is enabled.

Flow:
    1. ``upload_to_drive`` tool allocates an upload + signs a PUT URL.
    2. Client streams file bytes via ``PUT /drive-upload?uid=...&exp=...&sig=...``.
    3. Tool is re-invoked with the same ``path`` and finalizes the Drive upload
       from the staged bytes.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from config.enhanced_logging import setup_logger

logger = setup_logger()


def setup_drive_upload_endpoints(mcp: FastMCP) -> None:
    """Register the ``PUT /drive-upload`` HTTP endpoint."""

    @mcp.custom_route("/drive-upload", methods=["PUT"])
    async def drive_upload(request: Any):
        from starlette.responses import JSONResponse

        from config.settings import settings
        from drive.upload_staging import (
            get_allocation,
            mark_received,
            staged_path,
            verify_upload_url,
        )

        query = dict(request.query_params)
        upload_id = query.get("uid", "")
        exp = query.get("exp", "")
        sig = query.get("sig", "")

        if not all([upload_id, exp, sig]):
            return JSONResponse(
                {"error": "Missing required query parameters (uid, exp, sig)"},
                status_code=400,
            )

        valid, error = verify_upload_url(upload_id, exp, sig)
        if not valid:
            status = (
                410
                if "expired" in error.lower() or "already used" in error.lower()
                else 403
            )
            return JSONResponse({"error": error}, status_code=status)

        alloc = get_allocation(upload_id)
        if alloc is None:
            return JSONResponse({"error": "Allocation not found"}, status_code=404)

        max_bytes = settings.drive_upload_max_size_mb * 1024 * 1024
        target = staged_path(upload_id)

        # Stream the request body to disk to avoid loading large files in memory.
        # Enforce max-size during streaming.
        total = 0
        try:
            with open(target, "wb") as f:
                async for chunk in request.stream():
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        try:
                            import os

                            f.close()
                            os.unlink(target)
                        except OSError:
                            pass
                        return JSONResponse(
                            {
                                "error": (
                                    f"Upload exceeds max size "
                                    f"({settings.drive_upload_max_size_mb} MB)"
                                )
                            },
                            status_code=413,
                        )
                    f.write(chunk)
        except Exception as e:
            logger.error("Drive upload write failed: %s", e, exc_info=True)
            return JSONResponse(
                {"error": f"Failed to write staged upload: {e}"}, status_code=500
            )

        if total == 0:
            try:
                import os

                os.unlink(target)
            except OSError:
                pass
            return JSONResponse({"error": "Empty body"}, status_code=400)

        mark_received(upload_id, total)

        return JSONResponse(
            {
                "status": "received",
                "uploadId": upload_id,
                "bytes": total,
                "filename": alloc.filename,
                "nextStep": (
                    "Re-invoke upload_to_drive with the same path to finalize "
                    "the Drive upload."
                ),
            },
            status_code=200,
        )
