"""
Tunnel Manager for Cloudflare Tunnel Integration.

This module provides the TunnelManager class that coordinates the overall
tunnel functionality, including process management, resource registration,
and server lifecycle integration.
"""

import asyncio
import atexit
import logging
import os
import signal
import sys
import weakref
from typing import Dict, Optional, Union

from .process_controller import ProcessController

logger = logging.getLogger(__name__)


class TunnelManager:
    """
    Manager for Cloudflare tunnels in the FastMCP2 platform.
    
    This class coordinates the overall tunnel functionality, including:
    - Process management via ProcessController
    - Resource registration
    - Server lifecycle integration
    """
    
    _instance = None
    
    @classmethod
    def get_instance(cls) -> 'TunnelManager':
        """
        Get the singleton instance of TunnelManager.
        
        Returns:
            The TunnelManager instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        """Initialize the tunnel manager."""
        if TunnelManager._instance is not None:
            raise RuntimeError("TunnelManager is a singleton. Use get_instance() instead.")
            
        self.process_controller = ProcessController()
        self._register_shutdown_handlers()
        logger.info("TunnelManager initialized")
    
    async def start_tunnel(self, local_url: str = "http://localhost:8002/mcp") -> Dict[str, Union[str, int]]:
        """
        Start a new Cloudflare tunnel pointing to the specified local URL.
        
        Args:
            local_url: The local URL to expose through the tunnel
            
        Returns:
            Dict containing tunnel information including status, URL, and process ID
        """
        logger.info(f"Starting tunnel for {local_url}")
        result = await self.process_controller.start_tunnel(local_url)
        return result
    
    async def stop_tunnel(self) -> Dict[str, str]:
        """
        Stop the running Cloudflare tunnel.
        
        Returns:
            Dict containing status information
        """
        logger.info("Stopping tunnel")
        result = await self.process_controller.stop_tunnel()
        return result
    
    def get_status(self) -> Dict[str, Union[str, int, None]]:
        """
        Get the current status of the Cloudflare tunnel.
        
        Returns:
            Dict containing status information
        """
        return self.process_controller.get_status()
    
    def _register_shutdown_handlers(self) -> None:
        """Register handlers for server shutdown to ensure proper cleanup."""
        # Register atexit handler
        atexit.register(self._cleanup)
        
        # Register signal handlers
        if sys.platform != "win32":
            # On Unix-like systems
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, self._signal_handler)
        else:
            # On Windows
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, sig, frame) -> None:
        """
        Handle termination signals to ensure proper cleanup.
        
        Args:
            sig: Signal number
            frame: Current stack frame
        """
        logger.info(f"Received signal {sig}, cleaning up tunnel")
        self._cleanup()
        
        # Re-raise the signal after cleanup
        if sys.platform != "win32":
            # On Unix-like systems, reset the signal handler and re-raise
            signal.signal(sig, signal.SIG_DFL)
            os.kill(os.getpid(), sig)
        else:
            # On Windows, just exit
            sys.exit(1)
    
    def _cleanup(self) -> None:
        """Clean up resources when the server is shutting down."""
        logger.info("Cleaning up tunnel resources")
        
        # Get the event loop if available
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, schedule the stop_tunnel coroutine
                asyncio.create_task(self._async_cleanup())
            else:
                # If loop is not running, run the coroutine directly
                loop.run_until_complete(self.process_controller.stop_tunnel())
        except Exception as e:
            logger.error(f"Error during tunnel cleanup: {e}")
            
            # Fallback to synchronous termination
            if hasattr(self.process_controller, 'process') and self.process_controller.process is not None:
                try:
                    self.process_controller.process.terminate()
                    self.process_controller.process.wait(timeout=2)
                except Exception as e2:
                    logger.error(f"Error terminating process: {e2}")
    
    async def _async_cleanup(self) -> None:
        """Asynchronous cleanup for running event loops."""
        try:
            await self.process_controller.stop_tunnel()
        except Exception as e:
            logger.error(f"Error during async tunnel cleanup: {e}")


# Ensure proper cleanup by keeping a module-level reference
_manager_instance = None

def initialize() -> TunnelManager:
    """
    Initialize the TunnelManager singleton.
    
    This function should be called during server startup.
    
    Returns:
        The TunnelManager instance
    """
    global _manager_instance
    _manager_instance = TunnelManager.get_instance()
    return _manager_instance