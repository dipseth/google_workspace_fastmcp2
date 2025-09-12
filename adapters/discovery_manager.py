"""
Discovery Manager for Google Workspace MCP
Discovers available APIs and configurations
"""

import os
import json
import yaml
import logging

from config.enhanced_logging import setup_logger
logger = setup_logger()
from typing_extensions import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


class DiscoveryManager:
    """
    Discovers available APIs and configurations.
    Provides path resolution for modules and configs, supporting both JSON and YAML configuration files.
    """
    
    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize the discovery manager.
        
        Args:
            base_path: Base path for discovery (defaults to current directory)
        """
        self.base_path = Path(base_path) if base_path else Path.cwd()
        self._api_paths = {}
        self._config_paths = {}
        self._discovered = False
    
    def discover(self):
        """
        Discover available APIs and configurations.
        """
        if self._discovered:
            return
        
        logger.info(f"Starting discovery from base path: {self.base_path}")
        
        # Discover API modules
        self._discover_apis()
        
        # Discover configuration files
        self._discover_configs()
        
        self._discovered = True
        logger.info(f"Discovery complete. Found {len(self._api_paths)} APIs and {len(self._config_paths)} configs")
    
    def _discover_apis(self):
        """Discover API modules in the base path."""
        # Look for Python files that might contain APIs
        for py_file in self.base_path.rglob("*.py"):
            # Skip __init__.py and test files
            if py_file.name.startswith("__") or "test" in py_file.name.lower():
                continue
            
            # Check if file contains API-like classes
            if self._is_api_module(py_file):
                module_name = py_file.stem
                self._api_paths[module_name] = str(py_file)
                logger.debug(f"Discovered API module: {module_name} at {py_file}")
    
    def _discover_configs(self):
        """Discover configuration files."""
        # Look for JSON and YAML config files
        for config_file in self.base_path.rglob("*.json"):
            if "config" in config_file.name.lower():
                config_name = config_file.stem
                self._config_paths[config_name] = str(config_file)
                logger.debug(f"Discovered JSON config: {config_name} at {config_file}")
        
        for config_file in self.base_path.rglob("*.yaml"):
            if "config" in config_file.name.lower():
                config_name = config_file.stem
                self._config_paths[config_name] = str(config_file)
                logger.debug(f"Discovered YAML config: {config_name} at {config_file}")
        
        for config_file in self.base_path.rglob("*.yml"):
            if "config" in config_file.name.lower():
                config_name = config_file.stem
                self._config_paths[config_name] = str(config_file)
                logger.debug(f"Discovered YML config: {config_name} at {config_file}")
    
    def _is_api_module(self, py_file: Path) -> bool:
        """
        Check if a Python file contains API-like classes.
        
        Args:
            py_file: Path to Python file
            
        Returns:
            True if file appears to contain API classes
        """
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # Look for common API patterns
                api_indicators = [
                    'class.*API',
                    'class.*Adapter',
                    'def.*api',
                    '@server.tool',
                    'from mcp',
                    'BaseAPI'
                ]
                return any(indicator in content for indicator in api_indicators)
        except Exception as e:
            logger.debug(f"Error reading {py_file}: {e}")
            return False
    
    def get_api_path(self, api_name: str) -> Optional[str]:
        """
        Get the path to an API module.
        
        Args:
            api_name: Name of the API
            
        Returns:
            Path to the API module or None if not found
        """
        if not self._discovered:
            self.discover()
        return self._api_paths.get(api_name)
    
    def get_config_path(self, config_name: str) -> Optional[str]:
        """
        Get the path to a configuration file.
        
        Args:
            config_name: Name of the configuration
            
        Returns:
            Path to the configuration file or None if not found
        """
        if not self._discovered:
            self.discover()
        return self._config_paths.get(config_name)
    
    def list_apis(self) -> List[str]:
        """
        List all discovered API names.
        
        Returns:
            List of API names
        """
        if not self._discovered:
            self.discover()
        return list(self._api_paths.keys())
    
    def list_configs(self) -> List[str]:
        """
        List all discovered configuration names.
        
        Returns:
            List of configuration names
        """
        if not self._discovered:
            self.discover()
        return list(self._config_paths.keys())
    
    def load_config(self, config_name: str) -> Optional[Dict[str, Any]]:
        """
        Load a configuration file.
        
        Args:
            config_name: Name of the configuration
            
        Returns:
            Configuration dictionary or None if not found
        """
        config_path = self.get_config_path(config_name)
        if not config_path:
            return None
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                if config_path.endswith('.json'):
                    return json.load(f)
                elif config_path.endswith(('.yaml', '.yml')):
                    return yaml.safe_load(f)
                else:
                    logger.warning(f"Unsupported config file format: {config_path}")
                    return None
        except Exception as e:
            logger.error(f"Error loading config {config_name} from {config_path}: {e}")
            return None
    
    def get_api_paths(self) -> Dict[str, str]:
        """
        Get all discovered API paths.
        
        Returns:
            Dictionary mapping API names to their paths
        """
        if not self._discovered:
            self.discover()
        return self._api_paths.copy()
    
    def get_config_paths(self) -> Dict[str, str]:
        """
        Get all discovered configuration paths.
        
        Returns:
            Dictionary mapping config names to their paths
        """
        if not self._discovered:
            self.discover()
        return self._config_paths.copy()
    
    def refresh(self):
        """Refresh the discovery by clearing cache and re-discovering."""
        self._api_paths.clear()
        self._config_paths.clear()
        self._discovered = False
        self.discover()
        logger.info("Discovery refreshed")