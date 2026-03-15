"""
Domain Mixin for ModuleWrapper

Provides domain-level abstractions for ModuleWrapper clients:
- Module resolution via import name, pip package, or filesystem path
- Domain configuration via DomainConfig dataclass
- Lifecycle hooks (post_init, post_pipeline)
- Optional auto-install of missing pip packages

Init order: 55 (after InputResolverMixin:52, before CacheMixin)
"""

import importlib
import importlib.metadata
import importlib.util
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class DomainConfig:
    """Declarative configuration for a ModuleWrapper domain.

    Provides all domain-specific knobs without requiring the caller to
    implement singleton management or hook registration boilerplate.
    """

    module_name: str  # e.g. "card_framework.v2"
    pip_package: Optional[str] = (
        None  # e.g. "python-card-framework" (if different from module)
    )
    module_path: Optional[str] = None  # filesystem path for local modules
    auto_install: bool = False  # attempt pip install if missing
    priority_overrides: Dict[str, int] = field(default_factory=dict)
    nl_relationship_patterns: Dict[tuple, str] = field(default_factory=dict)
    post_init_hooks: List[Callable] = field(default_factory=list)
    post_pipeline_hooks: List[Callable] = field(default_factory=list)
    domain_label: str = ""  # human-readable label, e.g. "Google Chat Cards"

    def __post_init__(self):
        if not self.domain_label:
            self.domain_label = self.module_name


class DomainMixin:
    """
    Mixin that adds domain-level module resolution, configuration,
    and lifecycle hooks to ModuleWrapper.

    Expects the following attributes on self (from ModuleWrapperBase):
    - module: the resolved module object
    - module_name: str
    - components: Dict[str, ModuleComponent]
    """

    # --- Mixin dependency contract ---
    _MIXIN_PROVIDES: FrozenSet[str] = frozenset(
        {
            "domain_config",
            "resolve_module_auto",
            "ensure_package_installed",
            "register_domain_hooks",
            "run_domain_hooks",
        }
    )
    _MIXIN_REQUIRES: FrozenSet[str] = frozenset({"module", "module_name", "components"})
    _MIXIN_INIT_ORDER: int = 55

    def __init__(self, *args, **kwargs):
        """Initialize domain mixin state."""
        # Extract domain_config before passing to super
        self._domain_config: Optional[DomainConfig] = kwargs.pop("domain_config", None)

        # Hook registries
        self._domain_hooks: Dict[str, List[Callable]] = {
            "post_init": [],
            "post_pipeline": [],
        }

        super().__init__(*args, **kwargs)

        # If domain_config provided, register its hooks
        if self._domain_config:
            for hook in self._domain_config.post_init_hooks:
                self._domain_hooks["post_init"].append(hook)
            for hook in self._domain_config.post_pipeline_hooks:
                self._domain_hooks["post_pipeline"].append(hook)

    @property
    def domain_config(self) -> Optional[DomainConfig]:
        """Get the domain configuration, if any."""
        return self._domain_config

    def resolve_module_auto(
        self,
        module_or_name: Union[str, Any],
        pip_name: Optional[str] = None,
        module_path: Optional[str] = None,
        auto_install: bool = False,
    ) -> Any:
        """Resolve a module using multiple strategies.

        Tries in order:
        1. Import name — importlib.import_module()
        2. Pip package — install if missing and auto_install is True
        3. Filesystem path — importlib.util.spec_from_file_location()

        Args:
            module_or_name: Module object or import name string
            pip_name: Pip package name (if different from module name)
            module_path: Filesystem path for local modules
            auto_install: Whether to attempt pip install if import fails

        Returns:
            The resolved module object

        Raises:
            ValueError: If module cannot be resolved via any strategy
        """
        # Already a module object
        if not isinstance(module_or_name, str):
            return module_or_name

        # Strategy 1: Direct import
        try:
            return importlib.import_module(module_or_name)
        except ImportError:
            logger.debug(f"Direct import failed for {module_or_name}")

        # Strategy 2: Pip install then import
        if pip_name and auto_install:
            if self.ensure_package_installed(pip_name):
                try:
                    return importlib.import_module(module_or_name)
                except ImportError:
                    logger.debug(f"Import still failed after installing {pip_name}")

        # Strategy 3: Filesystem path
        if module_path:
            try:
                spec = importlib.util.spec_from_file_location(
                    module_or_name, module_path
                )
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[module_or_name] = mod
                    spec.loader.exec_module(mod)
                    return mod
            except Exception as e:
                logger.debug(f"Filesystem import failed for {module_path}: {e}")

        raise ValueError(
            f"Could not resolve module '{module_or_name}' via any strategy "
            f"(import, pip={pip_name}, path={module_path})"
        )

    def ensure_package_installed(
        self, pip_name: str, version_spec: Optional[str] = None
    ) -> bool:
        """Ensure a pip package is installed, optionally installing it.

        Installation is gated by:
        1. The auto_install flag on DomainConfig (default False)
        2. The MODULE_WRAPPER_AUTO_INSTALL env var (can override to disable globally)

        Args:
            pip_name: Package name on PyPI
            version_spec: Optional version specifier (e.g. ">=2.0")

        Returns:
            True if package is available (already installed or just installed)
        """
        # Check if already installed
        try:
            importlib.metadata.distribution(pip_name)
            return True
        except importlib.metadata.PackageNotFoundError:
            pass

        # Check auto_install gating
        env_override = os.environ.get("MODULE_WRAPPER_AUTO_INSTALL")
        if env_override is not None:
            # Env var explicitly set — use it
            auto_install = env_override.lower() in ("1", "true", "yes")
        elif self._domain_config:
            auto_install = self._domain_config.auto_install
        else:
            auto_install = False

        if not auto_install:
            logger.warning(
                f"Package '{pip_name}' not installed and auto_install is disabled. "
                f"Install manually: pip install {pip_name}"
            )
            return False

        # Attempt installation
        install_target = pip_name
        if version_spec:
            install_target = f"{pip_name}{version_spec}"

        logger.info(f"Installing package: {install_target}")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", install_target],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                logger.info(f"Successfully installed {install_target}")
                return True
            else:
                logger.error(f"Failed to install {install_target}: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            logger.error(f"Timed out installing {install_target}")
            return False
        except Exception as e:
            logger.error(f"Error installing {install_target}: {e}")
            return False

    def register_domain_hooks(
        self,
        post_init: Optional[List[Callable]] = None,
        post_pipeline: Optional[List[Callable]] = None,
    ) -> None:
        """Register lifecycle hooks for domain-specific operations.

        Args:
            post_init: Hooks to run after wrapper initialization (in-memory operations)
            post_pipeline: Hooks to run after Qdrant pipeline completes (write operations)
        """
        if post_init:
            self._domain_hooks["post_init"].extend(post_init)
        if post_pipeline:
            self._domain_hooks["post_pipeline"].extend(post_pipeline)

    def run_domain_hooks(self, phase: str) -> None:
        """Execute registered hooks for a lifecycle phase.

        Args:
            phase: "post_init" or "post_pipeline"
        """
        hooks = self._domain_hooks.get(phase, [])
        if not hooks:
            return

        label = self._domain_config.domain_label if self._domain_config else "unknown"
        logger.info(f"Running {len(hooks)} {phase} hooks for domain '{label}'")

        for hook in hooks:
            hook_name = getattr(hook, "__name__", str(hook))
            try:
                hook(self)
                logger.debug(f"  Hook '{hook_name}' completed")
            except Exception as e:
                logger.warning(f"  Hook '{hook_name}' failed: {e}")
