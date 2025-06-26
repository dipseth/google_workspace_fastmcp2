"""
API Adapters for Google Workspace MCP
This file contains the tool and agent creation logic for dynamic API adaptation.
"""

import os
import sys
import inspect
import importlib
import json
import yaml
import logging
from pydantic import BaseModel, Field, PrivateAttr, create_model, ConfigDict
from typing_extensions import Any, List, Tuple, Optional, Dict, Type, Union

# Import the base API
from .base_api import BaseAPI, APIMetadata

logger = logging.getLogger(__name__)

class APIAdapter(BaseAPI):
    """
    Dynamically adapts an existing API class to implement the BaseAPI interface.
    This allows any existing API class to be automatically wrapped and made available to agents.
    """
    
    def __init__(self, api_instance, metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize the adapter with the API instance to wrap.

        Args:
            api_instance: Instance of the API class to adapt
            metadata: Optional metadata to override defaults
        """
        self.api_instance = api_instance
        self.api_class = api_instance.__class__
        self.class_name = self.api_class.__name__
        self.module_name = self.api_class.__module__
        
        # Store for method information and their input models
        self.methods = {}
        
        # Default metadata values
        self._default_metadata = {
            "name": f"{self.class_name}",
            "description": f"API for {self.class_name.replace('API', '').lower()} services",
            "category": self.class_name.replace("API", "").lower(),
            "keywords": [self.class_name.replace("API", "").lower()],
            "requires_auth": False,
            "response_model": None,
            "version": "1.0.0",
        }

        # Override with provided metadata
        self._metadata = self._default_metadata.copy()
        if metadata:
            self._metadata.update(metadata)
            
        # Initialize method information and input models
        self._initialize_methods()

    def get_metadata(self) -> APIMetadata:
        """
        Return metadata about this API implementation.

        Returns:
            APIMetadata: Object containing name, description, etc.
        """
        return APIMetadata(**self._metadata)

    def _initialize_methods(self):
        """
        Initialize the methods and method_input_models attributes by scanning 
        all methods in the API instance and creating input models for each.
        """
        # Get all methods from the API instance and store their signatures
        self.methods = self.list_methods()

    def list_methods(self) -> Dict[str, Dict[str, Any]]:
        """
        Return a dictionary of available methods with their signatures.
        Automatically filters out private methods (starting with _).

        Returns:
            Dict[str, Dict[str, Any]]: Dictionary mapping method names to their metadata
        """
        methods = {}

        # Get all methods from the API instance
        for name, member in inspect.getmembers(self.api_instance, inspect.ismethod):
            # Skip private methods (starting with _)
            if name.startswith("_"):
                continue

            # Get method signature
            method_sig = self._get_method_signature(name)
            if method_sig:
                method_sig['input_model'] = self.create_input_model(name)
                methods[name] = method_sig

        return methods

    def __getattr__(self, name: str):
        """
        Proxy attribute access to the wrapped API instance.
        This allows calling methods on the adapter that will be forwarded to the API.

        Args:
            name: Attribute or method name

        Returns:
            The attribute or method from the wrapped API
        """
        # Get the attribute from the wrapped API instance
        attr = getattr(self.api_instance, name)

        # If it's a method, wrap it to maintain the adapter context
        if inspect.ismethod(attr):
            import functools
            
            @functools.wraps(attr)
            def wrapper(*args, **kwargs):
                return attr(*args, **kwargs)

            return wrapper

        return attr


def create_api_adapter(
    api_class_or_instance, metadata: Optional[Dict[str, Any]] = None
) -> APIAdapter:
    """
    Create an adapter for an API class or instance.

    Args:
        api_class_or_instance: API class or instance to adapt
        metadata: Optional metadata to override defaults

    Returns:
        APIAdapter instance wrapping the API
    """
    # If a class is provided, instantiate it
    if inspect.isclass(api_class_or_instance):
        api_instance = api_class_or_instance()
    else:
        api_instance = api_class_or_instance

    # Create and return the adapter
    return APIAdapter(api_instance, metadata)


def load_config_for_module(module_path):
    """
    Load YAML configuration files for a module.
    Looks for both default config (module_name.yaml) and named configs (module_name_*.yaml)
    
    Args:
        module_path: Path to the module file
    
    Returns:
        Dict of configuration name -> config dict
    """
    base_path = os.path.splitext(module_path)[0]
    module_name = os.path.basename(base_path)
    config_dir = os.path.dirname(module_path)
    
    logger.debug(f"Loading configs for module: {module_path}")
    logger.debug(f"Module name extracted: {module_name}")
    logger.debug(f"Module directory: {config_dir}")
    
    configs = {}
    
    # Look for default config file
    default_config_path = os.path.join(config_dir, f"{module_name}.yaml")
    logger.debug(f"Looking for default config: {default_config_path}")
    
    if os.path.exists(default_config_path):
        logger.debug(f"FOUND default config: {default_config_path}")
        try:
            with open(default_config_path, 'r') as f:
                configs['default'] = yaml.safe_load(f)
                logger.debug(f"Successfully loaded default configuration from {default_config_path}")
        except Exception as e:
            logger.error(f"Error loading config from {default_config_path}: {e}")
    else:
        logger.debug(f"Default config not found at: {default_config_path}")
    
    # Look for additional named configs (module_name_*.yaml)
    import glob
    config_pattern = os.path.join(config_dir, f"{module_name}_*.yaml")
    logger.debug(f"Looking for named configs with pattern: {config_pattern}")
    
    named_configs = glob.glob(config_pattern)
    logger.debug(f"Found {len(named_configs)} named config files: {named_configs}")
    
    for config_path in named_configs:
        try:
            # Extract config name from filename (e.g., "cards" from "chat_tools_cards.yaml")
            config_name = os.path.basename(config_path).replace(f"{module_name}_", "").replace(".yaml", "")
            logger.debug(f"Processing named config '{config_name}' from {config_path}")
            
            with open(config_path, 'r') as f:
                configs[config_name] = yaml.safe_load(f)
                logger.debug(f"Successfully loaded named configuration '{config_name}' from {config_path}")
        except Exception as e:
            logger.error(f"Error loading config from {config_path}: {e}")
    
    logger.debug(f"Config loading complete. Found {len(configs)} configurations: {list(configs.keys())}")
    return configs


def create_instance_from_config(module, class_name, config):
    """
    Create an instance of a class using configuration parameters.
    
    Args:
        module: The Python module containing the class
        class_name: Name of the class to instantiate
        config: Configuration dictionary
        
    Returns:
        Instance of the class
    """
    # General case for API classes
    cls = getattr(module, class_name)
    
    # If config has constructor_params key, use those parameters
    if 'constructor_params' in config:
        try:
            return cls(**config['constructor_params'])
        except Exception as e:
            logger.error(f"Error creating instance with constructor_params: {e}")
            return None
    else:
        # Try to instantiate without parameters
        try:
            return cls()
        except Exception as e:
            logger.error(f"Error creating instance without parameters: {e}")
            return None


def discover_and_adapt_apis(
    directory_path: str, package_name: Optional[str] = None
) -> Dict[str, APIAdapter]:
    """
    Scan a directory for Python files containing API classes and adapt them.

    Args:
        directory_path: Path to directory to scan
        package_name: Optional package name for imports

    Returns:
        Dict mapping API names to their adapters
    """
    adapters = {}
    
    # Determine if directory_path is a file or directory
    if os.path.isfile(directory_path):
        directory = os.path.dirname(directory_path)
        py_files = [directory_path]
    else:
        directory = directory_path
        # Get all Python files in the directory
        import glob
        py_files = glob.glob(os.path.join(directory_path, "*.py"))

    logger.info(f"Scanning directory: {directory_path}")
    logger.info(f"Python files found: {py_files}")

    # Add the directory to sys.path if not already there
    if directory not in sys.path:
        logger.info(f"Adding directory to sys.path: {directory}")
        sys.path.insert(0, directory)

    # Process each Python file
    for py_file in py_files:
        # Skip __init__.py and base_api.py
        if "__init__" in py_file or "base_api" in py_file:
            logger.info(f"Skipping file (init/base): {py_file}")
            continue

        try:
            # Get module name from file path
            module_name = os.path.basename(py_file).replace(".py", "")

            if package_name:
                module_path = f"{package_name}.{module_name}"
            else:
                module_path = module_name
                
            logger.info(f"Attempting to import module: {module_path} from {py_file}")

            # Load configurations for this module
            module_configs = load_config_for_module(py_file)
            
            # Handle potential import errors for each module individually
            try:
                # Import the module
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                else:
                    # Fallback to regular import if spec_from_file_location fails
                    module = importlib.import_module(module_path)
                    
                from abc import ABC

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    # Check if the class has "API" in the name or is a subclass of ABC
                    is_api_class = (
                        "API" in name and name != "BaseAPI" and name != "APIMetadata"
                    )

                    # Check if it's a subclass of ABC
                    is_abc_subclass = False
                    try:
                        is_abc_subclass = ABC in obj.__mro__
                    except (ImportError, AttributeError, TypeError):
                        pass

                    # Proceed if it's either an API class or an ABC subclass
                    if is_api_class or is_abc_subclass:
                        logger.info(
                            f"Found API class: {name} in {module_path} (API: {is_api_class}, ABC: {is_abc_subclass})"
                        )

                        # Create an instance and adapter
                        try:
                            # If there are configs for this module, create instances for each config
                            if module_configs:
                                for config_name, config in module_configs.items():
                                    instance = create_instance_from_config(module, name, config)
                                    if instance:
                                        # Create unique name for the adapter combining class name and config name
                                        adapter_name = f"{name}_{config_name}" if config_name != 'default' else name
                                        adapter = create_api_adapter(instance)
                                        adapters[adapter_name] = adapter
                                        logger.info(f"Successfully created adapter {adapter_name} with config {config_name}")
                            else:
                                # Default behavior - create instance without config
                                instance = obj()
                                adapter = create_api_adapter(instance)
                                adapters[name] = adapter
                                logger.info(f"Successfully created adapter for {name} (no config)")
                        except Exception as e:
                            logger.error(f"Error creating adapter for {name} from file {py_file}: {e}")
                            import traceback
                            logger.error(traceback.format_exc())
            except ImportError as e:
                # Log import errors but continue with other modules
                logger.error(f"Error importing module {module_path} from file {py_file}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        except Exception as e:
            logger.error(f"Error processing {py_file}: {e}")
            import traceback
            logger.error(traceback.format_exc())

    # Always log the actual directory and number of adapters found
    logger.info(f"Discovery in directory '{directory_path}' complete. {len(adapters)} adapters found.")
    if len(adapters) == 0:
        logger.warning(f"No compatible adapters found in directory '{directory_path}'.")
    else:
        logger.info(f"Adapters discovered: {list(adapters.keys())}")

    return adapters