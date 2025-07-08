"""
Utility functions for Cloudflare Tunnel Integration.

This module provides helper utilities for the tunnel integration.
"""

import logging
import os
import shutil
import subprocess
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def check_cloudflared_installed() -> bool:
    """
    Check if cloudflared is installed and available in the PATH.
    
    Returns:
        bool: True if cloudflared is installed, False otherwise
    """
    return shutil.which("cloudflared") is not None


def get_cloudflared_version() -> Optional[str]:
    """
    Get the installed cloudflared version.
    
    Returns:
        The cloudflared version string, or None if not available
    """
    try:
        if not check_cloudflared_installed():
            return None
            
        result = subprocess.run(
            ["cloudflared", "version"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            # Extract version from output
            version_line = result.stdout.strip()
            return version_line
            
        return None
    except Exception as e:
        logger.error(f"Error getting cloudflared version: {e}")
        return None


def get_installation_instructions() -> Dict[str, str]:
    """
    Get platform-specific installation instructions for cloudflared.
    
    Returns:
        Dict containing installation instructions for different platforms
    """
    return {
        "macos": "Install with Homebrew: brew install cloudflare/cloudflare/cloudflared",
        "linux": "Download from https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation",
        "windows": "Download from https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation",
        "general": "See installation guide at https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation"
    }


def get_platform_name() -> str:
    """
    Get the current platform name.
    
    Returns:
        String identifying the platform: 'macos', 'linux', 'windows', or 'unknown'
    """
    import platform
    system = platform.system().lower()
    
    if system == "darwin":
        return "macos"
    elif system == "linux":
        return "linux"
    elif system == "windows":
        return "windows"
    else:
        return "unknown"


def get_cloudflared_install_command() -> str:
    """
    Get the recommended installation command for the current platform.
    
    Returns:
        Installation command string
    """
    platform = get_platform_name()
    instructions = get_installation_instructions()
    
    return instructions.get(platform, instructions["general"])


def format_uptime(seconds: Optional[int]) -> str:
    """
    Format uptime seconds into a human-readable string.
    
    Args:
        seconds: Number of seconds, or None
        
    Returns:
        Formatted uptime string (e.g., "2h 15m 30s")
    """
    if seconds is None:
        return "0s"
        
    seconds = int(seconds)
    
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")
        
    return " ".join(parts)


def check_port_available(port: int, host: str = "localhost") -> Tuple[bool, Optional[str]]:
    """
    Check if a port is available on the specified host.
    
    Args:
        port: Port number to check
        host: Host to check (default: localhost)
        
    Returns:
        Tuple of (is_available, error_message)
    """
    import socket
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    
    try:
        # Try to connect to the port
        result = sock.connect_ex((host, port))
        
        # If result is 0, the port is in use
        is_available = result != 0
        
        error_message = None if is_available else f"Port {port} is already in use on {host}"
        
        return is_available, error_message
    except Exception as e:
        return False, f"Error checking port {port} on {host}: {e}"
    finally:
        sock.close()