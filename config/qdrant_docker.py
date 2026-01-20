"""
Qdrant Docker Auto-Launch Module

This module provides seamless automatic launching of Qdrant via Docker
when no remote Qdrant URL is configured or available.

Features:
- Auto-detects Docker availability
- Checks for existing Qdrant containers
- Launches Qdrant container with persistent storage
- Health checking and graceful startup
- Container lifecycle management

Usage:
    from config.qdrant_docker import ensure_qdrant_running

    # Returns True if Qdrant is available (either existing or newly launched)
    if ensure_qdrant_running():
        # Proceed with Qdrant client initialization
        ...
"""

import atexit
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

from config.enhanced_logging import setup_logger

logger = setup_logger()

# Global state for cleanup
_container_started_by_us = False
_container_name: Optional[str] = None


def is_running_in_docker() -> bool:
    """Check if we're running inside a Docker container."""
    # Check for .dockerenv file (created by Docker)
    if Path("/.dockerenv").exists():
        return True

    # Check cgroup for docker/container indicators
    try:
        with open("/proc/1/cgroup", "r") as f:
            content = f.read()
            if "docker" in content or "kubepods" in content or "containerd" in content:
                return True
    except (FileNotFoundError, PermissionError):
        pass

    # Check for container environment variable
    if os.environ.get("container") or os.environ.get("KUBERNETES_SERVICE_HOST"):
        return True

    return False


def is_docker_available() -> bool:
    """Check if Docker is installed and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False


def is_container_running(container_name: str) -> bool:
    """Check if a Docker container is running."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False


def container_exists(container_name: str) -> bool:
    """Check if a Docker container exists (running or stopped)."""
    try:
        result = subprocess.run(
            ["docker", "inspect", container_name],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False


def start_existing_container(container_name: str) -> bool:
    """Start an existing stopped container."""
    try:
        result = subprocess.run(
            ["docker", "start", container_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info(f"Started existing Qdrant container: {container_name}")
            return True
        else:
            logger.warning(f"Failed to start container: {result.stderr}")
            return False
    except Exception as e:
        logger.warning(f"Error starting container: {e}")
        return False


def launch_qdrant_container(
    container_name: str,
    image: str,
    port: int,
    grpc_port: int,
    data_dir: Optional[str] = None,
) -> bool:
    """
    Launch a new Qdrant Docker container.

    Args:
        container_name: Name for the Docker container
        image: Docker image to use (e.g., "qdrant/qdrant:latest")
        port: HTTP port to expose (default: 6333)
        grpc_port: gRPC port to expose (default: 6334)
        data_dir: Optional persistent data directory

    Returns:
        bool: True if container launched successfully
    """
    global _container_started_by_us, _container_name

    cmd = [
        "docker", "run",
        "-d",  # Detached mode
        "--name", container_name,
        "-p", f"{port}:6333",
        "-p", f"{grpc_port}:6334",
    ]

    # Add volume mount for persistent storage
    if data_dir:
        data_path = Path(data_dir).absolute()
        data_path.mkdir(parents=True, exist_ok=True)
        cmd.extend(["-v", f"{data_path}:/qdrant/storage"])
        logger.info(f"Qdrant data will persist to: {data_path}")

    # Add the image name
    cmd.append(image)

    try:
        logger.info(f"Launching Qdrant container: {container_name}")
        logger.debug(f"Docker command: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            _container_started_by_us = True
            _container_name = container_name
            logger.info(f"Qdrant container launched: {container_name}")
            return True
        else:
            logger.error(f"Failed to launch Qdrant container: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("Timeout launching Qdrant container")
        return False
    except Exception as e:
        logger.error(f"Error launching Qdrant container: {e}")
        return False


def wait_for_qdrant_ready(
    host: str = "localhost",
    port: int = 6333,
    timeout: int = 30,
    interval: float = 0.5,
) -> bool:
    """
    Wait for Qdrant to be ready to accept connections.

    Args:
        host: Qdrant host
        port: Qdrant HTTP port
        timeout: Maximum seconds to wait
        interval: Seconds between checks

    Returns:
        bool: True if Qdrant is ready
    """
    import urllib.request
    import urllib.error

    url = f"http://{host}:{port}/collections"
    start_time = time.time()

    logger.info(f"Waiting for Qdrant to be ready at {host}:{port}...")

    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    logger.info("Qdrant is ready!")
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, Exception):
            pass

        time.sleep(interval)

    logger.warning(f"Qdrant not ready after {timeout} seconds")
    return False


def check_qdrant_reachable(host: str = "localhost", port: int = 6333) -> bool:
    """
    Quick check if Qdrant is reachable.

    Args:
        host: Qdrant host
        port: Qdrant HTTP port

    Returns:
        bool: True if Qdrant responds
    """
    import urllib.request
    import urllib.error

    url = f"http://{host}:{port}/collections"

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def stop_container(container_name: str) -> bool:
    """Stop a Docker container."""
    try:
        result = subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def cleanup_on_exit():
    """Cleanup handler to stop container on program exit if we started it."""
    global _container_started_by_us, _container_name

    if _container_started_by_us and _container_name:
        # Check settings to see if we should stop on exit
        try:
            from config.settings import settings
            if getattr(settings, 'qdrant_docker_stop_on_exit', False):
                logger.info(f"Stopping Qdrant container on exit: {_container_name}")
                stop_container(_container_name)
        except Exception:
            pass


# Register cleanup handler
atexit.register(cleanup_on_exit)


def ensure_qdrant_running() -> Tuple[bool, str]:
    """
    Ensure Qdrant is running, auto-launching via Docker if needed.

    This is the main entry point for seamless Qdrant availability.

    Flow:
    1. Check if Qdrant is already reachable at configured URL
    2. If not, check if Docker auto-launch is enabled
    3. If enabled, check for existing container and start/create as needed
    4. Wait for Qdrant to be ready

    Returns:
        Tuple[bool, str]: (success, url) - Whether Qdrant is available and the URL to use
    """
    try:
        from config.settings import settings
    except ImportError:
        logger.error("Could not import settings")
        return False, ""

    # Get configuration
    qdrant_url = settings.qdrant_url
    qdrant_host = settings.qdrant_host or "localhost"
    qdrant_port = settings.qdrant_port or 6333

    # Check if auto-launch is enabled (default: True for local URLs)
    auto_launch = getattr(settings, 'qdrant_auto_launch', True)

    # Determine if this is a remote/cloud URL (don't auto-launch for remote)
    is_local = qdrant_host in ("localhost", "127.0.0.1", "0.0.0.0")
    is_cloud = qdrant_url and ("cloud" in qdrant_url or "qdrant.io" in qdrant_url)

    # First, check if Qdrant is already reachable
    if check_qdrant_reachable(qdrant_host, qdrant_port):
        logger.info(f"Qdrant already running at {qdrant_host}:{qdrant_port}")
        return True, qdrant_url or f"http://{qdrant_host}:{qdrant_port}"

    # If it's a cloud/remote URL and not reachable, don't try to auto-launch
    if is_cloud or not is_local:
        logger.warning(f"Remote Qdrant at {qdrant_url} is not reachable")
        return False, ""

    # Check if auto-launch is disabled
    if not auto_launch:
        logger.info("Qdrant auto-launch disabled, skipping Docker setup")
        return False, ""

    # Check if we're running inside a Docker container
    if is_running_in_docker():
        logger.info(
            "Running inside Docker container - auto-launch disabled. "
            "Use docker-compose to manage Qdrant service."
        )
        return False, ""

    # Check if Docker is available
    if not is_docker_available():
        logger.warning(
            "Docker not available - cannot auto-launch Qdrant. "
            "Install Docker or configure QDRANT_URL to point to an existing instance."
        )
        return False, ""

    # Get Docker configuration
    container_name = getattr(settings, 'qdrant_docker_container_name', 'mcp-qdrant')
    image = getattr(settings, 'qdrant_docker_image', 'qdrant/qdrant:latest')
    grpc_port = getattr(settings, 'qdrant_docker_grpc_port', 6334)
    data_dir = getattr(settings, 'qdrant_docker_data_dir', None)

    # Use credentials dir for data if not explicitly set
    if not data_dir:
        data_dir = str(Path(settings.credentials_dir) / "qdrant_data")

    # Check if container already exists
    if container_exists(container_name):
        if is_container_running(container_name):
            logger.info(f"Qdrant container already running: {container_name}")
        else:
            logger.info(f"Starting stopped Qdrant container: {container_name}")
            if not start_existing_container(container_name):
                logger.error(f"Failed to start existing container: {container_name}")
                return False, ""
    else:
        # Launch new container
        if not launch_qdrant_container(
            container_name=container_name,
            image=image,
            port=qdrant_port,
            grpc_port=grpc_port,
            data_dir=data_dir,
        ):
            logger.error("Failed to launch Qdrant container")
            return False, ""

    # Wait for Qdrant to be ready
    startup_timeout = getattr(settings, 'qdrant_docker_startup_timeout', 30)
    if wait_for_qdrant_ready(qdrant_host, qdrant_port, timeout=startup_timeout):
        url = f"http://{qdrant_host}:{qdrant_port}"
        logger.info(f"Qdrant running at {url}")
        return True, url

    logger.error("Qdrant container started but not responding")
    return False, ""


def get_qdrant_status() -> dict:
    """
    Get the current status of Qdrant and Docker configuration.

    Returns:
        dict: Status information including:
            - docker_available: bool
            - qdrant_reachable: bool
            - container_name: str
            - container_exists: bool
            - container_running: bool
            - started_by_us: bool
    """
    try:
        from config.settings import settings

        host = settings.qdrant_host or "localhost"
        port = settings.qdrant_port or 6333
        container_name = getattr(settings, 'qdrant_docker_container_name', 'mcp-qdrant')

        return {
            "docker_available": is_docker_available(),
            "running_in_docker": is_running_in_docker(),
            "qdrant_reachable": check_qdrant_reachable(host, port),
            "qdrant_url": settings.qdrant_url,
            "qdrant_host": host,
            "qdrant_port": port,
            "container_name": container_name,
            "container_exists": container_exists(container_name),
            "container_running": is_container_running(container_name),
            "started_by_us": _container_started_by_us,
            "auto_launch_enabled": getattr(settings, 'qdrant_auto_launch', True),
        }
    except Exception as e:
        return {"error": str(e)}
