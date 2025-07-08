"""
Process Controller for Cloudflare Tunnel Integration.

This module handles the creation, monitoring, and termination of the cloudflared
subprocess that establishes the Cloudflare tunnel.
"""

import asyncio
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
from typing import Dict, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Regular expression to extract the tunnel URL from cloudflared output
TUNNEL_URL_PATTERN = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


class ProcessController:
    """Controller for managing the cloudflared subprocess."""

    def __init__(self):
        """Initialize the process controller."""
        self.process: Optional[subprocess.Popen] = None
        self.tunnel_url: Optional[str] = None
        self.status: str = "inactive"
        self.error_message: Optional[str] = None
        self.output_reader_task: Optional[asyncio.Task] = None
        self.start_time: Optional[float] = None

    async def start_tunnel(self, local_url: str = "http://localhost:8002/mcp") -> Dict[str, Union[str, int]]:
        """
        Start a new Cloudflare tunnel pointing to the specified local URL.

        Args:
            local_url: The local URL to expose through the tunnel (default: http://localhost:8002/mcp)

        Returns:
            Dict containing tunnel information including status, URL, and process ID

        Raises:
            RuntimeError: If cloudflared is not installed or if the tunnel fails to start
        """
        # Check if cloudflared is installed
        if not self._check_cloudflared_installed():
            self.status = "error"
            self.error_message = "cloudflared is not installed. Please install it first."
            raise RuntimeError(self.error_message)

        # Check if a tunnel is already running
        if self.process is not None and self.process.poll() is None:
            return {
                "status": self.status,
                "url": self.tunnel_url,
                "pid": self.process.pid,
                "message": "Tunnel is already running"
            }

        # Reset state
        self.tunnel_url = None
        self.error_message = None
        self.status = "starting"

        try:
            # Start cloudflared process
            cmd = ["cloudflared", "tunnel", "--url", local_url]
            
            # Use shell=False for better security and process management
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            self.start_time = asyncio.get_event_loop().time()
            
            # Start output reader task
            self.output_reader_task = asyncio.create_task(self._read_process_output())
            
            # Wait for tunnel URL to be available or error to occur
            url_or_error = await self._wait_for_tunnel_url()
            
            if self.error_message:
                self.status = "error"
                raise RuntimeError(f"Failed to start tunnel: {self.error_message}")
            
            self.status = "active"
            return {
                "status": self.status,
                "url": self.tunnel_url,
                "pid": self.process.pid,
                "message": "Tunnel started successfully"
            }
            
        except Exception as e:
            self.status = "error"
            self.error_message = str(e)
            logger.error(f"Error starting tunnel: {e}")
            
            # Clean up if process was started
            if self.process is not None:
                self._terminate_process()
                
            raise RuntimeError(f"Failed to start tunnel: {e}")

    async def stop_tunnel(self) -> Dict[str, str]:
        """
        Stop the running Cloudflare tunnel.

        Returns:
            Dict containing status information

        Raises:
            RuntimeError: If no tunnel is running or if the tunnel fails to stop
        """
        if self.process is None or self.process.poll() is not None:
            self.status = "inactive"
            return {
                "status": self.status,
                "message": "No tunnel is running"
            }

        try:
            self.status = "stopping"
            self._terminate_process()
            
            # Wait for process to terminate
            for _ in range(10):  # Wait up to 1 second
                if self.process.poll() is not None:
                    break
                await asyncio.sleep(0.1)
                
            # Force kill if still running
            if self.process.poll() is None:
                self.process.kill()
                await asyncio.sleep(0.5)
                
            self.status = "inactive"
            return {
                "status": self.status,
                "message": "Tunnel stopped successfully"
            }
            
        except Exception as e:
            self.status = "error"
            self.error_message = str(e)
            logger.error(f"Error stopping tunnel: {e}")
            raise RuntimeError(f"Failed to stop tunnel: {e}")

    def get_status(self) -> Dict[str, Union[str, int, None]]:
        """
        Get the current status of the Cloudflare tunnel.

        Returns:
            Dict containing status information
        """
        result = {
            "status": self.status,
            "url": self.tunnel_url,
            "error": self.error_message,
            "pid": None,
            "uptime_seconds": None
        }
        
        if self.process is not None:
            result["pid"] = self.process.pid
            
            # Check if process is still running
            if self.process.poll() is None:
                if self.start_time is not None:
                    result["uptime_seconds"] = int(asyncio.get_event_loop().time() - self.start_time)
            else:
                # Process has terminated
                if self.status != "inactive" and self.status != "error":
                    self.status = "inactive"
                    result["status"] = self.status
                    
        return result

    def _check_cloudflared_installed(self) -> bool:
        """
        Check if cloudflared is installed and available in the PATH.

        Returns:
            bool: True if cloudflared is installed, False otherwise
        """
        return shutil.which("cloudflared") is not None

    def _terminate_process(self) -> None:
        """Terminate the cloudflared process."""
        if self.process is None:
            return
            
        try:
            # Cancel output reader task
            if self.output_reader_task is not None:
                self.output_reader_task.cancel()
                
            # Send SIGTERM to process group
            if sys.platform != "win32":
                # On Unix-like systems, use process group
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    # Process might already be gone
                    pass
            else:
                # On Windows
                self.process.terminate()
                
        except Exception as e:
            logger.error(f"Error terminating process: {e}")

    async def _read_process_output(self) -> None:
        """
        Read and process the output from the cloudflared process.
        
        This coroutine runs until the process terminates or is cancelled.
        It extracts the tunnel URL from the output and logs all output.
        """
        if self.process is None or self.process.stdout is None:
            return
            
        try:
            while True:
                line = await asyncio.to_thread(self.process.stdout.readline)
                if not line:
                    break
                    
                # Log the output
                logger.debug(f"cloudflared: {line.strip()}")
                
                # Extract tunnel URL if not already found
                if self.tunnel_url is None:
                    match = TUNNEL_URL_PATTERN.search(line)
                    if match:
                        self.tunnel_url = match.group(0)
                        logger.info(f"Tunnel URL: {self.tunnel_url}")
                        
                # Check for error messages
                if "error" in line.lower() or "failed" in line.lower():
                    self.error_message = line.strip()
                    logger.error(f"Tunnel error: {self.error_message}")
                    
        except asyncio.CancelledError:
            # Task was cancelled, which is expected during cleanup
            pass
        except Exception as e:
            logger.error(f"Error reading process output: {e}")
            self.error_message = str(e)
            
        finally:
            # Process has terminated or reading was interrupted
            if self.process is not None and self.process.poll() is not None:
                logger.info(f"cloudflared process terminated with exit code {self.process.returncode}")
                
                # Update status if process terminated unexpectedly
                if self.status == "active":
                    self.status = "error" if self.process.returncode != 0 else "inactive"
                    if self.process.returncode != 0:
                        self.error_message = f"Process terminated with exit code {self.process.returncode}"

    async def _wait_for_tunnel_url(self, timeout: float = 10.0) -> Optional[str]:
        """
        Wait for the tunnel URL to become available or for an error to occur.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            The tunnel URL if successful, None otherwise
        """
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            # Check if URL is available
            if self.tunnel_url is not None:
                return self.tunnel_url
                
            # Check if error occurred
            if self.error_message is not None:
                return None
                
            # Check if process terminated
            if self.process is not None and self.process.poll() is not None:
                self.error_message = f"Process terminated with exit code {self.process.returncode}"
                return None
                
            # Wait a bit before checking again
            await asyncio.sleep(0.1)
            
        # Timeout occurred
        self.error_message = "Timeout waiting for tunnel URL"
        return None