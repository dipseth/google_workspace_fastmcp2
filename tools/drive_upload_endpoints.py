"""HTTP endpoint for receiving client→server file uploads via signed URLs.

Inverse of ``/attachment-download``. Registered by
``setup_drive_upload_endpoints(mcp)`` in ``server.py``. Active when
``settings.drive_upload_client_fs`` is enabled.

Flow:
    1. ``upload_to_drive`` / ``upload_photos`` signs a PUT URL.
    2. Client streams file bytes via ``PUT /drive-upload?t=...&sig=...``.
    3. Tool is re-invoked with the same ``path`` and finalizes the upload
       from the staged bytes.

The endpoint keeps no state of its own: the signed token says where the bytes
go, so the PUT may land on a different replica from the two tool calls.
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
            commit_staged,
            incoming_path,
            verify_upload_url,
        )

        query = dict(request.query_params)
        token = query.get("t", "")
        sig = query.get("sig", "")

        if not all([token, sig]):
            return JSONResponse(
                {"error": "Missing required query parameters (t, sig)"},
                status_code=400,
            )

        valid, error, payload = verify_upload_url(token, sig)
        if not valid or payload is None:
            status = (
                410
                if "expired" in error.lower() or "already used" in error.lower()
                else 403
            )
            return JSONResponse({"error": error}, status_code=status)

        max_bytes = settings.drive_upload_max_size_mb * 1024 * 1024
        upload_id = payload["uid"]
        target = incoming_path(upload_id)

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

        try:
            await commit_staged(payload, target, total)
        except Exception as e:
            logger.error("Drive upload commit failed: %s", e, exc_info=True)
            try:
                import os

                os.unlink(target)
            except OSError:
                pass
            return JSONResponse(
                {"error": f"Failed to store staged upload: {e}"}, status_code=500
            )

        return JSONResponse(
            {
                "status": "received",
                "uploadId": upload_id,
                "bytes": total,
                "filename": payload.get("fn"),
                "nextStep": (
                    "Re-invoke the tool that issued this URL with the same "
                    "path to finalize the upload."
                ),
            },
            status_code=200,
        )
