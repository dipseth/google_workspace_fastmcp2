"""
Component Indexing Mixin

Provides component extraction, module indexing, and Qdrant storage
for the ModuleWrapper system.
"""

import hashlib
import importlib
import inspect
import logging
from datetime import UTC, datetime
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from .core import ModuleComponent

logger = logging.getLogger(__name__)


# =============================================================================
# STANDARD LIBRARY DETECTION
# =============================================================================

# Common standard library modules to skip
STD_LIB_PREFIXES = [
    "builtins",
    "collections",
    "typing",
    "types",
    "functools",
    "itertools",
    "operator",
    "re",
    "os",
    "sys",
    "json",
    "datetime",
    "time",
    "random",
    "math",
    "inspect",
    "ast",
    "copy",
    "abc",
    "enum",
    "importlib",
    "pathlib",
    "io",
    "warnings",
    "uuid",
    "logging",
    "email",
    "zipfile",
    "textwrap",
    "posixpath",
    "token",
    "tokenize",
    "keyword",
    "linecache",
    "dis",
    "socket",
    "selectors",
    "select",
    "ssl",
    "http",
    "urllib",
    "base64",
    "struct",
    "bisect",
    "contextlib",
    "hashlib",
    "tempfile",
    "quopri",
    "binascii",
    "stat",
    "ipaddress",
    "copyreg",
    "errno",
    "array",
    "codecs",
    "decimal",
    "numbers",
    "threading",
    "zlib",
    "bz2",
    "lzma",
    "shutil",
    "fnmatch",
    "posix",
    "string",
]

# Common third-party libraries to skip
THIRD_PARTY_PREFIXES = [
    "numpy",
    "pandas",
    "matplotlib",
    "scipy",
    "sklearn",
    "tensorflow",
    "torch",
    "keras",
    "django",
    "flask",
    "requests",
    "bs4",
    "selenium",
    "sqlalchemy",
    "pytest",
    "unittest",
    "nose",
    "marshmallow",
    "dataclasses_json",
    "stringcase",
    "qdrant_client",
    "sentence_transformers",
]


# =============================================================================
# INDEXING MIXIN
# =============================================================================


class IndexingMixin:
    """
    Mixin providing component extraction and indexing functionality.

    Expects the following attributes on self:
    - module: The wrapped module
    - module_name, _module_name: Module name properties
    - components: Dict[str, ModuleComponent]
    - root_components: Dict[str, ModuleComponent]
    - client: Qdrant client
    - embedder: Embedding model
    - collection_name: str
    - index_nested, index_private: bool
    - max_depth: int
    - skip_standard_library: bool
    - include_modules, exclude_modules: List[str]
    - collection_needs_indexing: bool
    """

    # Tracking state
    _visited_modules: Set[str]
    _current_depth: int

    def _is_standard_library(self, module_name: str) -> bool:
        """
        Check if a module is part of the Python standard library.

        Args:
            module_name: Name of the module

        Returns:
            True if the module is part of the standard library
        """
        for prefix in STD_LIB_PREFIXES:
            if module_name == prefix or module_name.startswith(f"{prefix}."):
                return True

        for prefix in THIRD_PARTY_PREFIXES:
            if module_name == prefix or module_name.startswith(f"{prefix}."):
                return True

        return False

    def _should_include_module(self, module_name: str, current_depth: int) -> bool:
        """
        Determine if a module should be included in indexing.

        Args:
            module_name: Name of the module
            current_depth: Current recursion depth

        Returns:
            True if the module should be included
        """
        # Skip standard library modules if configured
        if self.skip_standard_library and self._is_standard_library(module_name):
            logger.debug(f"Skipping standard library module {module_name}")
            return False

        # If include_modules is provided, only include modules with these prefixes
        if self.include_modules:
            for prefix in self.include_modules:
                if module_name == prefix or module_name.startswith(f"{prefix}."):
                    break
            else:
                logger.debug(f"Skipping module {module_name} (not in include list)")
                return False

        # If exclude_modules is provided, skip modules with these prefixes
        if self.exclude_modules:
            for prefix in self.exclude_modules:
                if module_name == prefix or module_name.startswith(f"{prefix}."):
                    logger.debug(f"Skipping module {module_name} (in exclude list)")
                    return False

        return True

    def _should_skip_object(self, name: str, obj: Any) -> bool:
        """
        Determine if an object should be skipped during indexing.

        Args:
            name: Name of the object
            obj: The actual object

        Returns:
            True if the object should be skipped
        """
        try:
            # Skip typing module generics
            if str(type(obj)).startswith("<class 'typing."):
                return True

            # Skip built-in types
            if isinstance(obj, type) and obj.__module__ == "builtins":
                return True

            # Skip method descriptors and built-in functions
            if type(obj).__name__ in (
                "method_descriptor",
                "builtin_function_or_method",
                "getset_descriptor",
                "wrapper_descriptor",
            ):
                return True

            # Skip objects with problematic __repr__ methods
            if hasattr(obj, "__repr__"):
                try:
                    repr(obj)
                except Exception:
                    return True

            # Skip objects with problematic __str__ methods
            if hasattr(obj, "__str__"):
                try:
                    str(obj)
                except Exception:
                    return True

            return False

        except Exception:
            # If any error occurs during the checks, skip the object
            return True

    def _create_component(
        self,
        name: str,
        obj: Any,
        module_path: str,
        parent: Optional[ModuleComponent] = None,
    ) -> ModuleComponent:
        """
        Create a component object.

        Args:
            name: Name of the component
            obj: The actual object
            module_path: Module path
            parent: Parent component

        Returns:
            ModuleComponent object
        """
        try:
            # Skip objects that should be skipped
            if self._should_skip_object(name, obj):
                logger.debug(f"Skipping object {name} of type {type(obj)}")
                return ModuleComponent(
                    name=name,
                    obj=None,
                    module_path=module_path,
                    component_type="skipped",
                    docstring="",
                    source="",
                    parent=parent,
                )

            # Determine component type safely
            component_type = "variable"
            try:
                if inspect.isclass(obj):
                    component_type = "class"
                elif inspect.isfunction(obj):
                    component_type = "function"
                elif inspect.ismethod(obj):
                    component_type = "method"
                elif inspect.ismodule(obj):
                    component_type = "module"
            except Exception as e:
                logger.debug(f"Error determining component type for {name}: {e}")

            # Get docstring safely
            docstring = ""
            try:
                docstring = inspect.getdoc(obj) or ""
            except Exception as e:
                logger.debug(f"Error getting docstring for {name}: {e}")

            # Get source code if possible
            source = ""
            try:
                if callable(obj) or inspect.isclass(obj):
                    source = inspect.getsource(obj)
            except Exception as e:
                logger.debug(f"Could not get source for {name}: {e}")

            return ModuleComponent(
                name=name,
                obj=obj,
                module_path=module_path,
                component_type=component_type,
                docstring=docstring,
                source=source,
                parent=parent,
            )

        except Exception as e:
            logger.warning(f"Error creating component for {name}: {e}")
            return ModuleComponent(
                name=name,
                obj=None,
                module_path=module_path,
                component_type="error",
                docstring=f"Error: {str(e)}",
                source="",
                parent=parent,
            )

    def _index_nested_components(self, parent: ModuleComponent):
        """
        Index nested components (methods, attributes) of a class.

        Args:
            parent: Parent component (usually a class)
        """
        try:
            # Only index nested components for classes
            if parent.component_type != "class":
                return

            # Skip if parent object is None
            if parent.obj is None:
                return

            # Get all members of the class safely
            try:
                members = inspect.getmembers(parent.obj)
            except Exception as e:
                logger.debug(f"Error getting members of class {parent.name}: {e}")
                return

            # Process each member
            for name, obj in members:
                try:
                    # Skip private members if not indexing them
                    if name.startswith("_") and not self.index_private:
                        continue

                    # Skip problematic objects
                    if self._should_skip_object(name, obj):
                        continue

                    # Create component
                    component = self._create_component(
                        name=name,
                        obj=obj,
                        module_path=parent.module_path,
                        parent=parent,
                    )

                    # Add to parent
                    parent.add_child(component)

                    # Store in flat components dictionary
                    self.components[component.full_path] = component
                except Exception as e:
                    logger.debug(f"Error processing class member {name}: {e}")
        except Exception as e:
            logger.warning(f"Error indexing nested components for {parent.name}: {e}")

    def _index_submodule(self, name: str, submodule: Any):
        """
        Recursively index a submodule's components.

        Args:
            name: Name of the submodule
            submodule: The submodule object
        """
        try:
            # Skip if already visited
            if (
                not hasattr(submodule, "__name__")
                or submodule.__name__ in self._visited_modules
            ):
                return

            # Mark as visited
            self._visited_modules.add(submodule.__name__)

            # Increment depth counter
            self._current_depth += 1
            current_depth = self._current_depth

            # Ensure we don't exceed max depth
            if current_depth > self.max_depth:
                logger.debug(f"Maximum depth reached, skipping submodule {name}")
                self._current_depth -= 1
                return

            # Check if module should be included
            if hasattr(submodule, "__name__"):
                if not self._should_include_module(submodule.__name__, current_depth):
                    self._current_depth -= 1
                    return

            logger.info(
                f"Recursively indexing submodule {submodule.__name__} (depth: {current_depth}/{self.max_depth})..."
            )

            # Get all submodule components safely
            try:
                members = inspect.getmembers(submodule)
            except Exception as e:
                logger.warning(f"Error getting members of submodule: {e}")
                members = []

            # Process each member
            for sub_name, sub_obj in members:
                try:
                    # Skip private members if not indexing them
                    if sub_name.startswith("_") and not self.index_private:
                        continue

                    # Skip problematic objects
                    if self._should_skip_object(sub_name, sub_obj):
                        continue

                    # Create component
                    component = self._create_component(
                        sub_name, sub_obj, getattr(submodule, "__name__", name)
                    )

                    # Store in flat components dictionary
                    self.components[component.full_path] = component

                    # Index nested components if requested
                    if self.index_nested:
                        try:
                            self._index_nested_components(component)
                        except Exception as e:
                            logger.debug(
                                f"Error indexing nested components for {sub_name}: {e}"
                            )

                        # Recursively index submodules
                        if (
                            inspect.ismodule(sub_obj)
                            and hasattr(sub_obj, "__name__")
                            and sub_obj.__name__ not in self._visited_modules
                            and current_depth < self.max_depth
                            and self._should_include_module(
                                sub_obj.__name__, current_depth + 1
                            )
                        ):
                            self._index_submodule(sub_name, sub_obj)
                except Exception as e:
                    logger.debug(f"Error processing submodule member {sub_name}: {e}")

        except Exception as e:
            logger.warning(f"Error indexing submodule {name}: {e}")
        finally:
            self._current_depth -= 1

    def _index_widgets_module(self, widgets_module):
        """
        Special indexing for widgets modules.

        Args:
            widgets_module: The widgets module to index
        """
        logger.info(f"Indexing widgets module: {widgets_module.__name__}")
        try:
            for name, obj in inspect.getmembers(widgets_module):
                # Skip private members if not indexing them
                if name.startswith("_") and not self.index_private:
                    continue

                # Skip objects that should be skipped
                if self._should_skip_object(name, obj):
                    continue

                # Create component
                component = self._create_component(name, obj, self.module_name)

                # Store with special path
                component_path = f"{self.module_name}.widgets.{name}"
                self.components[component_path] = component

                logger.info(f"Added widget component: {component_path}")

                # Index nested components if requested
                if self.index_nested and component.component_type == "class":
                    try:
                        self._index_nested_components(component)
                    except Exception as e:
                        logger.debug(
                            f"Error indexing nested components for widget {name}: {e}"
                        )
        except Exception as e:
            logger.warning(f"Error indexing widgets module: {e}")

    def _index_module_components(self):
        """Index all components in the module."""
        try:
            # Check if indexing is needed
            if not getattr(self, "collection_needs_indexing", True):
                logger.info(
                    f"Skipping indexing for module {self.module_name} - collection already has data"
                )
                self._load_components_from_collection()
                return

            logger.info(
                f"Indexing components in module {self.module_name} (max depth: {self.max_depth})..."
            )

            # Reset visited modules and depth counter
            self._visited_modules = set()
            self._current_depth = 0

            # Add the main module to visited modules
            self._visited_modules.add(self.module.__name__)

            # Get all module components
            for name, obj in inspect.getmembers(self.module):
                # Skip private members if not indexing them
                if name.startswith("_") and not self.index_private:
                    continue

                # Skip standard library modules at root level
                if (
                    inspect.ismodule(obj)
                    and hasattr(obj, "__name__")
                    and not self._should_include_module(obj.__name__, 0)
                ):
                    continue

                # Create component
                component = self._create_component(name, obj, self.module_name)

                # Store in root components
                self.root_components[name] = component

                # Store in flat components dictionary
                self.components[component.full_path] = component

                # Index nested components if requested
                if self.index_nested:
                    self._index_nested_components(component)

                    # Recursively index submodules
                    if (
                        inspect.ismodule(obj)
                        and obj.__name__ not in self._visited_modules
                        and self._current_depth < self.max_depth
                        and hasattr(obj, "__name__")
                        and self._should_include_module(obj.__name__, 1)
                    ):
                        self._index_submodule(name, obj)

            # Special handling for widgets modules
            if hasattr(self.module, "widgets"):
                logger.info(
                    f"Special handling for {self.module_name}.widgets module..."
                )
                try:
                    widgets_module = getattr(self.module, "widgets")
                    if inspect.ismodule(widgets_module):
                        self._index_widgets_module(widgets_module)
                except Exception as e:
                    logger.warning(f"Error accessing widgets module: {e}")

            # Store components in Qdrant
            self._store_components_in_qdrant()

            logger.info(
                f"Indexed {len(self.components)} components in module {self.module_name}"
            )

        except Exception as e:
            logger.error(f"Failed to index module components: {e}", exc_info=True)
            raise

    def _load_components_from_collection(self):
        """Load components from existing Qdrant collection into memory."""
        try:
            logger.info(
                f"Loading existing components from collection {self.collection_name}..."
            )

            offset = None
            loaded_count = 0

            while True:
                scroll_result = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )

                points, next_offset = scroll_result

                if not points:
                    break

                for point in points:
                    payload = point.payload
                    if not payload:
                        continue

                    path = payload.get("full_path")
                    if not path:
                        continue

                    name = payload.get("name", "")
                    module_path = payload.get("module_path", self.module_name)
                    component_type = payload.get("type", "variable")
                    docstring = payload.get("docstring", "")
                    source = payload.get("source", "")

                    # Try to resolve the actual object
                    obj = self._resolve_object_from_path(path)

                    component = ModuleComponent(
                        name=name,
                        obj=obj,
                        module_path=module_path,
                        component_type=component_type,
                        docstring=docstring,
                        source=source,
                        parent=None,
                    )

                    self.components[path] = component
                    loaded_count += 1

                offset = next_offset
                if offset is None:
                    break

            logger.info(f"Loaded {loaded_count} components from collection")

        except Exception as e:
            logger.error(
                f"Failed to load components from collection: {e}", exc_info=True
            )

    def _resolve_object_from_path(self, path: str) -> Any:
        """Resolve an object from its full path."""
        try:
            parts = path.split(".")

            # Normalize path
            if parts and parts[0] == self.module_name:
                parts = parts[1:]

            obj = self.module
            for part in parts:
                try:
                    obj = getattr(obj, part)
                except AttributeError:
                    # Try importing as module
                    module_candidate = f"{getattr(obj, '__name__', '')}.{part}".lstrip(
                        "."
                    )
                    try:
                        obj = importlib.import_module(module_candidate)
                    except (ImportError, ModuleNotFoundError):
                        return None
            return obj
        except Exception:
            return None

    def _generate_embedding_text(self, component: ModuleComponent) -> str:
        """
        Generate minimal text for embedding a component.

        Args:
            component: The component to generate text for

        Returns:
            Text for embedding
        """
        text_parts = [
            f"Name: {component.name}",
            f"Type: {component.component_type}",
            f"Path: {component.full_path}",
        ]

        # Add only the first line of the docstring if available
        if component.docstring:
            first_line = component.docstring.split("\n")[0]
            text_parts.append(f"Documentation: {first_line}")

        return "\n".join(text_parts)

    def _batch_items(self, items, batch_size: int) -> Iterator[List]:
        """Helper method to batch items for processing."""
        batch = []
        for item in items:
            batch.append(item)
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def _store_components_in_qdrant(self):
        """Store all components in Qdrant with deterministic IDs."""
        try:
            from .qdrant_mixin import _get_qdrant_imports

            component_count = len(self.components)
            logger.info(f"Storing {component_count} components in Qdrant...")

            _, qdrant_models = _get_qdrant_imports()

            index_version = datetime.now(UTC).isoformat()
            batch_size = 50
            processed = 0

            for batch_idx, batch_items in enumerate(
                self._batch_items(self.components.items(), batch_size)
            ):
                points = []
                for path, component in batch_items:
                    # Generate text for embedding
                    embed_text = self._generate_embedding_text(component)

                    # Generate embedding using FastEmbed
                    embedding_list = list(self.embedder.embed([embed_text]))
                    embedding = embedding_list[0] if embedding_list else None

                    if embedding is None:
                        logger.warning(
                            f"Failed to generate embedding for component: {path}"
                        )
                        continue

                    # Create deterministic ID
                    id_string = f"{self.collection_name}:{path}"
                    hash_hex = hashlib.sha256(id_string.encode()).hexdigest()
                    component_id = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"

                    # Convert numpy array to list if needed
                    if hasattr(embedding, "tolist"):
                        vector_list = embedding.tolist()
                    else:
                        vector_list = list(embedding)

                    # Add version info to payload
                    payload = component.to_dict()
                    payload["indexed_at"] = index_version
                    payload["module_version"] = getattr(
                        self.module, "__version__", "unknown"
                    )

                    # Add symbol for this component
                    comp_name = component.name
                    if comp_name and hasattr(self, "symbol_mapping"):
                        symbol = self.symbol_mapping.get(comp_name)
                        if symbol:
                            payload["symbol"] = symbol

                    point = qdrant_models["PointStruct"](
                        id=component_id,
                        vector=vector_list,
                        payload=payload,
                    )

                    points.append(point)

                # Store batch in Qdrant
                self.client.upsert(collection_name=self.collection_name, points=points)

                processed += len(points)
                logger.info(
                    f"Stored batch {batch_idx + 1} ({processed}/{component_count} components)"
                )

            logger.info(f"Stored {processed} components in Qdrant")

        except Exception as e:
            logger.error(f"Failed to store components in Qdrant: {e}", exc_info=True)
            raise

    def _index_components_colbert(self):
        """Index components using ColBERT multi-vector embeddings."""
        if not self.enable_colbert or not getattr(self, "_colbert_initialized", False):
            logger.warning(
                "ColBERT not enabled or initialized, skipping ColBERT indexing"
            )
            return

        try:
            from .qdrant_mixin import _get_qdrant_imports

            _, qdrant_models = _get_qdrant_imports()

            # Check if collection already has data
            collection_info = self.client.get_collection(self.colbert_collection_name)
            if collection_info.points_count > 0 and not self.force_reindex:
                logger.info(
                    f"ColBERT collection already has {collection_info.points_count} points, skipping indexing"
                )
                return

            logger.info(
                f"Indexing {len(self.components)} components with ColBERT embeddings..."
            )

            index_version = datetime.now(UTC).isoformat()
            batch_size = 10
            processed = 0

            for batch_idx, batch_items in enumerate(
                self._batch_items(list(self.components.items()), batch_size)
            ):
                points = []
                for path, component in batch_items:
                    embed_text = self._generate_embedding_text(component)

                    try:
                        embedding_result = list(
                            self.colbert_embedder.embed([embed_text])
                        )
                        if not embedding_result:
                            continue

                        multi_vector = embedding_result[0]
                        if hasattr(multi_vector, "tolist"):
                            vector_list = multi_vector.tolist()
                        else:
                            vector_list = [list(v) for v in multi_vector]

                    except Exception as embed_error:
                        logger.warning(
                            f"ColBERT embedding failed for {path}: {embed_error}"
                        )
                        continue

                    id_string = f"{self.colbert_collection_name}:{path}"
                    hash_hex = hashlib.sha256(id_string.encode()).hexdigest()
                    component_id = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"

                    payload = component.to_dict()
                    payload["indexed_at"] = index_version
                    payload["module_version"] = getattr(
                        self.module, "__version__", "unknown"
                    )
                    payload["embedding_type"] = "colbert"

                    point = qdrant_models["PointStruct"](
                        id=component_id,
                        vector={"colbert": vector_list},
                        payload=payload,
                    )
                    points.append(point)

                if points:
                    self.client.upsert(
                        collection_name=self.colbert_collection_name, points=points
                    )
                    processed += len(points)
                    logger.info(
                        f"ColBERT batch {batch_idx + 1}: stored {len(points)} components ({processed} total)"
                    )

            logger.info(f"ColBERT indexing complete: {processed} components indexed")

        except Exception as e:
            logger.error(f"Failed to index components with ColBERT: {e}", exc_info=True)
            raise


# Export for convenience
__all__ = [
    "IndexingMixin",
    "STD_LIB_PREFIXES",
    "THIRD_PARTY_PREFIXES",
]
