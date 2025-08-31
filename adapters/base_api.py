"""
BaseAPI Interface - Abstract Base Class that all API implementations should follow.
This standardizes how agents can discover and use APIs.
Adapted for Google Workspace MCP project.
"""

import inspect
import json
from abc import ABC, abstractmethod
from typing_extensions import Dict, List, Type, TypeVar, get_type_hints, Union
from typing_extensions import Any, Literal, TypedDict, Optional
from pydantic import BaseModel, create_model, Field, ConfigDict
import os
import sys
import re
from collections import Counter
import builtins
import logging

# Define a TypeVar for the return type
STOP_WORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'if', 'because', 'as', 'what',
    'when', 'where', 'how', 'to', 'of', 'for', 'with', 'in', 'on', 'by',
    'is', 'are', 'was', 'were', 'be', 'been', 'this', 'that', 'these', 
    'those', 'it', 'its', 'from', 'at', 'which', 'each'
}
T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)

class APIMetadata(BaseModel):
    """Metadata for an API implementation"""

    name: str
    description: str
    category: str
    keywords: List[str]
    requires_auth: bool = False
    response_model: Optional[Type[BaseModel]] = None
    version: str = "1.0.0"
    input_parameters: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return self.model_dump()


class BaseAPI(ABC):
    """
    Base API interface that all API implementations should implement.
    This provides a standard way for agents to discover and use APIs.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @abstractmethod
    def get_metadata(self) -> APIMetadata:
        """
        Return metadata about this API implementation.

        Returns:
            APIMetadata: Object containing name, description, etc.
        """
        pass

    @abstractmethod
    def list_methods(self) -> Dict[str, Dict[str, Any]]:
        """
        Return a dictionary of available methods with their signatures.

        Returns:
            Dict[str, Dict[str, Any]]: Dictionary mapping method names to their metadata
        """
        pass

    def extract_keywords_from_doc(self, text: str, max_keywords: int = 5, 
                                 deduplication_threshold: float = 0.9, 
                                 window_size: int = 1) -> List[str]:
        """
        Extract keywords from the provided text using YAKE if available.
        Falls back to simple frequency-based extraction if YAKE is not installed.
        Filters out common Pydantic and documentation-related terms.
        
        Args:
            text: The text to extract keywords from
            max_keywords: Maximum number of keywords to extract
            deduplication_threshold: Threshold for deduplication of keywords
            window_size: Size of word n-grams
            
        Returns:
            List[str]: List of extracted keywords
        """
        if not text:
            return []
            
        # Common Pydantic and documentation words to filter out
        pydantic_doc_words = {
            # Common types
            'str', 'string', 'int', 'integer', 'float', 'bool', 'boolean', 'list', 
            'dict', 'tuple', 'set', 'any', 'none', 'optional', 'union',
            'type', 'object', 'model',
            # Pydantic related
            'basemodel', 'field', 'config', 'schema', 'json', 'model_dump', 'to_dict',
            'pydantic', 'model_config', 'configdict',
            # Type annotations
            'list', 'dict', 'optional', 'union', 'tuple', 'set', 'callable',
            'typeddict', 'typing', 'type', 'typevar', 'generic', 'annotation',
            # Documentation terms
            'param', 'parameter', 'arg', 'argument', 'kwarg', 'returns', 'return',
            'raises', 'yield', 'yields', 'note', 'example', 'examples', 'warning',
            'parameters', 'args', 'kwargs', 'function', 'method', 'class',
            'default', 'required', 'options', 'description', 'specify',
            'doc', 'docstring', 'documentation',
            # Common doc sections
            'attributes', 'methods', 'parameters', 'returns', 'raises', 'examples',
            'see', 'also', 'notes', 'warnings', 'references', 'todo',
            # API and general words
            'api', 'endpoint', 'request', 'response', 'input', 'output', 'data',
            'user', 'service', 'client', 'server', 'interface', 'call', 'auth',
            'authentication', 'authorization', 'token', 'header', 'body', 'query',
            'parameter', 'resource', 'value', 'error', 'success', 'result',
            'status', 'code', 'get', 'post', 'put', 'delete', 'patch', 'update',
            'create', 'read', 'write', 'fetch', 'retrieve', 'process', 'handle',
            'implement', 'provide', 'receive', 'send', 'pass', 'return', 'use', 'using',
            'implementation', 'information', 'additional', 'contain', 'contains'
        }
        
        # Combine with common stop words
        pydantic_doc_words = pydantic_doc_words.union(STOP_WORDS)
            
        # Try to use YAKE for keyword extraction if available
        try:
            import yake
            
            # Initialize YAKE extractor with language detection
            language = "en"  # Default to English
            max_ngram_size = 1  # Allow extraction of phrases up to 3 words
                        
            kw_extractor = yake.KeywordExtractor(
                lan=language,
                n=max_ngram_size,
                dedupLim=deduplication_threshold,
                dedupFunc='seqm',
                windowsSize=window_size,
                top=max_keywords * 2,  # Extract more keywords initially to allow filtering
                features=None
            )

            # Add stop words to YAKE's internal stopword list first
            kw_extractor.stopword_set = kw_extractor.stopword_set.union(STOP_WORDS)

            # Extract keywords (returns list of tuples with (keyword, score))
            # Lower score means more relevant in YAKE
            keywords = kw_extractor.extract_keywords(text)
            
            # Filter out pydantic and documentation-related words
            filtered_keywords = []
            for kw, score in keywords:
                # Skip single-word keywords that are in our filter list
                if kw.lower() in pydantic_doc_words:
                    continue
                
                # For multi-word keywords, check if all words are in filter list
                words_in_kw = kw.lower().split()
                if len(words_in_kw) > 1 and all(word in pydantic_doc_words for word in words_in_kw):
                    continue
                    
                filtered_keywords.append((kw, score))
                
                # Stop once we have enough keywords
                if len(filtered_keywords) >= max_keywords:
                    break
            
            # Extract just the keywords (not scores) and return
            return [kw for kw, _ in filtered_keywords]
            
        except ImportError:
            # Fall back to simple frequency-based extraction if YAKE is not available
            import re
            from collections import Counter

            # Basic preprocessing
            # Convert to lowercase and remove special characters
            clean_text = re.sub(r'[^\w\s]', '', text.lower())
            
            # Remove common stop words (simplified list) plus pydantic/doc words
            stop_words = STOP_WORDS
            
            # Combine standard stop words with pydantic/doc words
            all_filter_words = stop_words.union(pydantic_doc_words)
            
            # Split into words and filter out stop words and pydantic/doc words
            words = [word for word in clean_text.split() if word not in all_filter_words and len(word) > 2]
            
            # Count word frequency
            word_counts = Counter(words)
            
            # Return the most common words
            return [word for word, _ in word_counts.most_common(max_keywords)]
    
    def _get_method_signature(self, method_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the signature of a method.

        Args:
            method_name: Name of the method

        Returns:
            Dict with method signature info or None if method not found
        """
        # Get the method
        method = getattr(self, method_name, None)
        if not method or not callable(method):
            return None

        # Get signature
        sig = inspect.signature(method)

        # Get docstring
        docstring = inspect.getdoc(method) or ""

        # Get type hints
        type_hints = get_type_hints(method)

        # Build parameters dict
        parameters = {}
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            # Try to get type from type_hints first, fall back to annotation if not found
            param_type_obj = type_hints.get(name, None)
            
            # If type_hints doesn't have the type, try to use param.annotation
            if param_type_obj is None and param.annotation != inspect.Parameter.empty:
                param_type_obj = param.annotation
            else:
                param_type_obj = Any  # Default to Any if no type information is available
                
            # Get the type name as a string
            if hasattr(param_type_obj, "__name__"):
                param_type = param_type_obj.__name__
            else:
                # Handle complex types like Union, List, etc.
                param_type = str(param_type_obj)

            parameters[name] = {
                "type": param_type,
                "default": (
                    None if param.default is inspect.Parameter.empty else param.default
                ),
                "required": param.default is inspect.Parameter.empty
                and param.kind != inspect.Parameter.VAR_POSITIONAL
                and param.kind != inspect.Parameter.VAR_KEYWORD,
            }

        # Return method info
        return {
            "name": method_name,
            "docstring": docstring,
            "parameters": parameters,
            "return_type": type_hints.get("return", Any).__name__,
        }

    def create_input_model(self, method_name: str) -> Type[BaseModel]:
        """
        Create a Pydantic model for the input parameters of a method.

        Args:
            method_name: Name of the method

        Returns:
            Type[BaseModel]: Pydantic model for the input parameters
        """
        # Get method signature
        sig_info = self._get_method_signature(method_name)
        if not sig_info:
            raise ValueError(f"Method {method_name} not found")

        # Create field definitions for the model
        field_definitions = {}

        # Get parameters from method signature
        method_params = sig_info.get("parameters", {})
        field_definitions = {}
        
        if "parameters" in sig_info:
            for param_name, param_info in method_params.items():
                # Parse the type information
                type_str = param_info.get('type')
                description = param_info.get('description', '')
                # Get required status and default value from the signature info
                required = param_info.get('required', False)
                default = param_info.get('default')
                
                # --- Improved type parsing logic ---
                import typing

                def resolve_type(type_str):
                    # Remove 'typing.' prefix for compatibility with eval
                    clean_type_str = type_str.replace("typing.", "")
                    typing_namespace = {
                        **vars(typing),
                        **vars(builtins),
                        "Any": Any,
                        "BaseModel": BaseModel,
                    }
                    
                    # Handle basic Python types directly to ensure proper display in schema
                    if clean_type_str == "str":
                        return str
                    elif clean_type_str == "int":
                        return int
                    elif clean_type_str == "float": 
                        return float
                    elif clean_type_str == "bool":
                        return bool
                    elif clean_type_str == "list":
                        return list
                    elif clean_type_str == "dict":
                        return dict
                    
                    # Handle qualified names like 'folium.Map'
                    if "." in clean_type_str and not clean_type_str.startswith("Union"):
                        module_name, type_name = clean_type_str.rsplit(".", 1)
                        try:
                            mod = __import__(module_name, fromlist=[type_name])
                            return getattr(mod, type_name)
                        except Exception:
                            return typing_namespace.get(type_name, Any)
                    try:
                        return eval(clean_type_str, typing_namespace)
                    except Exception:
                        return Any

                param_type = resolve_type(type_str)
                # Create field definition tuple (type, field_info)
                # Use Field to explicitly set default behavior based on 'required' status
                if required and param_name not in ['args', 'kwargs']:
                    # Required field: Use Ellipsis (...) as the default marker in Field
                    field_definitions[param_name] = (param_type, Field(description=description, default=...))
                elif param_name not in ['args', 'kwargs']:
                    # Optional field: Use the actual default value (which might be None) in Field
                    field_definitions[param_name] = (param_type, Field(description=description, default=default))

            # Create and return the model
            model_name = f"{method_name.title()}Input"
            
            # Python 3.12 with Pydantic v2 compatibility
            model = create_model(
                model_name,
                **field_definitions,
            )
            # Use model_config instead of __config__ for Pydantic v2
            model.model_config = ConfigDict(arbitrary_types_allowed=True)
            return model