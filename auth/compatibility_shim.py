"""
Compatibility Shim for Legacy Scope Usage

This module provides backward compatibility for legacy scope usage patterns
while automatically redirecting to the new centralized scope registry.
"""

import logging
from typing_extensions import Dict, List, Any, Optional, Union
from .scope_registry import ScopeRegistry, ServiceScopeManager

logger = logging.getLogger(__name__)


class CompatibilityShim:
    """Provide backward compatibility for legacy scope usage"""
    
    # Cache for performance
    _legacy_scope_groups_cache: Optional[Dict[str, str]] = None
    _legacy_service_defaults_cache: Optional[Dict[str, Dict]] = None
    _legacy_drive_scopes_cache: Optional[List[str]] = None
    
    @classmethod
    def get_legacy_scope_groups(cls) -> Dict[str, str]:
        """
        Provide legacy SCOPE_GROUPS format for service_manager.py
        
        This method converts the new registry format back to the old SCOPE_GROUPS
        dictionary format used by service_manager.py, ensuring zero-breaking changes.
        """
        if cls._legacy_scope_groups_cache is not None:
            return cls._legacy_scope_groups_cache
        
        logger.info("COMPATIBILITY: Generating legacy SCOPE_GROUPS format from registry")
        
        legacy_groups = {}
        
        # Convert service scopes to legacy format
        for service, scopes in ScopeRegistry.GOOGLE_API_SCOPES.items():
            if service == "base":
                # Handle base scopes without service prefix
                for scope_name, scope_url in scopes.items():
                    legacy_groups[scope_name] = scope_url
            else:
                # Add service prefix for other scopes
                for scope_name, scope_url in scopes.items():
                    legacy_key = f"{service}_{scope_name}"
                    legacy_groups[legacy_key] = scope_url
        
        # Add specific legacy mappings that were in the original SCOPE_GROUPS
        legacy_mappings = {
            # Drive legacy names
            "drive_read": ScopeRegistry.GOOGLE_API_SCOPES["drive"]["readonly"],
            "drive_file": ScopeRegistry.GOOGLE_API_SCOPES["drive"]["file"],
            "drive_appdata": ScopeRegistry.GOOGLE_API_SCOPES["drive"]["appdata"],
            "drive_metadata": ScopeRegistry.GOOGLE_API_SCOPES["drive"]["metadata"],
            "drive_metadata_readonly": ScopeRegistry.GOOGLE_API_SCOPES["drive"]["metadata_readonly"],
            "drive_photos_readonly": ScopeRegistry.GOOGLE_API_SCOPES["drive"]["photos_readonly"],
            "drive_scripts": ScopeRegistry.GOOGLE_API_SCOPES["drive"]["scripts"],
            
            # Gmail legacy names
            "gmail_read": ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["readonly"],
            "gmail_send": ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["send"],
            "gmail_compose": ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["compose"],
            "gmail_modify": ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["modify"],
            "gmail_labels": ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["labels"],
            "gmail_full": ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["full"],
            "gmail_insert": ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["insert"],
            "gmail_metadata": ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["metadata"],
            "gmail_settings_basic": ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["settings_basic"],
            "gmail_settings_sharing": ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["settings_sharing"],
            
            # Calendar legacy names
            "calendar_read": ScopeRegistry.GOOGLE_API_SCOPES["calendar"]["readonly"],
            "calendar_events": ScopeRegistry.GOOGLE_API_SCOPES["calendar"]["events"],
            "calendar_full": ScopeRegistry.GOOGLE_API_SCOPES["calendar"]["full"],
            "calendar_settings_read": ScopeRegistry.GOOGLE_API_SCOPES["calendar"]["settings_readonly"],
            
            # Docs legacy names
            "docs_read": ScopeRegistry.GOOGLE_API_SCOPES["docs"]["readonly"],
            "docs_write": ScopeRegistry.GOOGLE_API_SCOPES["docs"]["full"],
            
            # Sheets legacy names
            "sheets_read": ScopeRegistry.GOOGLE_API_SCOPES["sheets"]["readonly"],
            "sheets_write": ScopeRegistry.GOOGLE_API_SCOPES["sheets"]["full"],
            "sheets_full": ScopeRegistry.GOOGLE_API_SCOPES["sheets"]["full"],
            
            # Chat legacy names
            "chat_read": ScopeRegistry.GOOGLE_API_SCOPES["chat"]["messages_readonly"],
            "chat_write": ScopeRegistry.GOOGLE_API_SCOPES["chat"]["messages"],
            "chat_spaces": ScopeRegistry.GOOGLE_API_SCOPES["chat"]["spaces"],
            "chat_memberships_readonly": ScopeRegistry.GOOGLE_API_SCOPES["chat"]["memberships_readonly"],
            "chat_memberships": ScopeRegistry.GOOGLE_API_SCOPES["chat"]["memberships"],
            
            # Forms legacy names
            "forms": ScopeRegistry.GOOGLE_API_SCOPES["forms"]["body"],
            "forms_read": ScopeRegistry.GOOGLE_API_SCOPES["forms"]["body_readonly"],
            "forms_responses_read": ScopeRegistry.GOOGLE_API_SCOPES["forms"]["responses_readonly"],
            "forms_body": ScopeRegistry.GOOGLE_API_SCOPES["forms"]["body"],
            "forms_body_readonly": ScopeRegistry.GOOGLE_API_SCOPES["forms"]["body_readonly"],
            "forms_responses_readonly": ScopeRegistry.GOOGLE_API_SCOPES["forms"]["responses_readonly"],
            
            # Slides legacy names
            "slides": ScopeRegistry.GOOGLE_API_SCOPES["slides"]["full"],
            "slides_read": ScopeRegistry.GOOGLE_API_SCOPES["slides"]["readonly"],
            
            # Photos legacy names (using only valid scopes)
            "photos_read": ScopeRegistry.GOOGLE_API_SCOPES["photos"]["readonly"],
            "photos_append": ScopeRegistry.GOOGLE_API_SCOPES["photos"]["appendonly"],
            "photos_readonly_appcreated": ScopeRegistry.GOOGLE_API_SCOPES["photos"]["readonly_appcreated"],
            "photos_edit_appcreated": ScopeRegistry.GOOGLE_API_SCOPES["photos"]["edit_appcreated"],
            # PhotosLibrary legacy names (for backwards compatibility)
            "photoslibrary_read": ScopeRegistry.GOOGLE_API_SCOPES["photos"]["readonly"],
            "photoslibrary_append": ScopeRegistry.GOOGLE_API_SCOPES["photos"]["appendonly"],
            "photoslibrary_readonly_appcreated": ScopeRegistry.GOOGLE_API_SCOPES["photos"]["readonly_appcreated"],
            "photoslibrary_edit_appcreated": ScopeRegistry.GOOGLE_API_SCOPES["photos"]["edit_appcreated"],
            
            # Admin legacy names
            "admin_users": ScopeRegistry.GOOGLE_API_SCOPES["admin"]["users"],
            "admin_groups": ScopeRegistry.GOOGLE_API_SCOPES["admin"]["groups"],
            "admin_roles": ScopeRegistry.GOOGLE_API_SCOPES["admin"]["roles"],
            "admin_orgunit": ScopeRegistry.GOOGLE_API_SCOPES["admin"]["orgunit"],
            
            # Cloud platform legacy names
            "cloud_platform": ScopeRegistry.GOOGLE_API_SCOPES["cloud"]["platform"],
            "cloud_platform_read_only": ScopeRegistry.GOOGLE_API_SCOPES["cloud"]["platform_readonly"],
            
            # Other services
            "userinfo_profile": ScopeRegistry.GOOGLE_API_SCOPES["base"]["userinfo_profile"],
            "userinfo_email": ScopeRegistry.GOOGLE_API_SCOPES["base"]["userinfo_email"],
            "tasks_read": ScopeRegistry.GOOGLE_API_SCOPES["tasks"]["readonly"],
            "tasks_full": ScopeRegistry.GOOGLE_API_SCOPES["tasks"]["full"],
            "youtube_read": ScopeRegistry.GOOGLE_API_SCOPES["youtube"]["readonly"],
            "youtube_upload": ScopeRegistry.GOOGLE_API_SCOPES["youtube"]["upload"],
            "youtube_full": ScopeRegistry.GOOGLE_API_SCOPES["youtube"]["full"],
            "script_projects": ScopeRegistry.GOOGLE_API_SCOPES["script"]["projects"],
            "script_deployments": ScopeRegistry.GOOGLE_API_SCOPES["script"]["deployments"],
        }
        
        # Merge legacy mappings
        legacy_groups.update(legacy_mappings)
        
        # Cache the result
        cls._legacy_scope_groups_cache = legacy_groups
        
        logger.info(f"COMPATIBILITY: Generated {len(legacy_groups)} legacy scope mappings")
        return legacy_groups
    
    @classmethod
    def get_legacy_service_defaults(cls) -> Dict[str, Dict]:
        """
        Provide legacy SERVICE_DEFAULTS format for service_helpers.py
        
        This method converts the new registry to the old SERVICE_DEFAULTS
        dictionary format, ensuring backward compatibility.
        """
        if cls._legacy_service_defaults_cache is not None:
            return cls._legacy_service_defaults_cache
        
        logger.info("COMPATIBILITY: Generating legacy SERVICE_DEFAULTS format from registry")
        
        legacy_defaults = {}
        
        # Map services to their legacy default scope names
        service_mappings = {
            "drive": {
                "default_scopes": ["drive_file", "drive_read"],
                "version": "v3",
                "description": "Google Drive service"
            },
            "gmail": {
                "default_scopes": ["gmail_read", "gmail_send", "gmail_compose", "gmail_modify", "gmail_labels"],
                "version": "v1",
                "description": "Gmail service"
            },
            "calendar": {
                "default_scopes": ["calendar_read", "calendar_events", "calendar_full"],
                "version": "v3",
                "description": "Google Calendar service"
            },
            "docs": {
                "default_scopes": ["docs_read", "docs_write"],
                "version": "v1",
                "description": "Google Docs service"
            },
            "sheets": {
                "default_scopes": ["sheets_read", "sheets_write"],
                "version": "v4",
                "description": "Google Sheets service"
            },
            "chat": {
                "default_scopes": ["chat_read", "chat_write"],
                "version": "v1",
                "description": "Google Chat service"
            },
            "forms": {
                "default_scopes": ["forms", "forms_read", "forms_responses_read"],
                "version": "v1",
                "description": "Google Forms service"
            },
            "slides": {
                "default_scopes": ["slides", "slides_read"],
                "version": "v1",
                "description": "Google Slides service"
            },
            "photos": {
                "default_scopes": ["photos_read", "photos_append"],
                "version": "v1",
                "description": "Google Photos service"
            },
            "photoslibrary": {
                "default_scopes": ["photos_read", "photos_append"],
                "version": "v1",
                "description": "Google Photos Library API service"
            },
            "tasks": {
                "default_scopes": ["tasks_read", "tasks_full"],
                "version": "v1",
                "description": "Google Tasks API service"
            }
        }
        
        legacy_defaults = service_mappings
        
        # Cache the result
        cls._legacy_service_defaults_cache = legacy_defaults
        
        logger.info(f"COMPATIBILITY: Generated legacy SERVICE_DEFAULTS for {len(legacy_defaults)} services")
        return legacy_defaults
    
    @classmethod
    def get_legacy_drive_scopes(cls) -> List[str]:
        """
        Provide legacy drive_scopes format for settings.py
        
        This method provides the comprehensive OAuth scopes list using
        oauth_comprehensive as the single source of truth.
        """
        if cls._legacy_drive_scopes_cache is not None:
            return cls._legacy_drive_scopes_cache
        
        logger.info("COMPATIBILITY: Generating legacy drive_scopes from oauth_comprehensive group")
        
        # Use oauth_comprehensive as the single source of truth
        oauth_scopes = ScopeRegistry.resolve_scope_group("oauth_comprehensive")
        
        # Cache the result
        cls._legacy_drive_scopes_cache = oauth_scopes
        
        logger.info(f"COMPATIBILITY: Generated {len(oauth_scopes)} legacy drive_scopes from oauth_comprehensive")
        return oauth_scopes
    
    @classmethod
    def get_legacy_oauth_endpoint_scopes(cls) -> List[str]:
        """
        Provide legacy scope format for OAuth endpoints
        
        Returns scopes for OAuth endpoints - now uses oauth_comprehensive as single source of truth
        """
        logger.info("COMPATIBILITY: Generating OAuth endpoint scopes from oauth_comprehensive")
        
        # Use oauth_comprehensive as the single source of truth
        return ScopeRegistry.resolve_scope_group("oauth_comprehensive")
    
    @classmethod
    def get_legacy_dcr_scope_defaults(cls) -> str:
        """
        Provide legacy scope defaults for dynamic client registration
        
        Returns the default scope string used in dynamic_client_registration.py
        """
        logger.info("COMPATIBILITY: Generating legacy DCR scope defaults")
        
        # Ensure DCR default scopes include Gmail Settings scopes so clients can request filters/forwarding
        default_scopes = [
            # Base
            ScopeRegistry.GOOGLE_API_SCOPES["base"]["openid"],
            ScopeRegistry.GOOGLE_API_SCOPES["base"]["userinfo_email"],
            ScopeRegistry.GOOGLE_API_SCOPES["base"]["userinfo_profile"],
            # Drive basics
            ScopeRegistry.GOOGLE_API_SCOPES["drive"]["readonly"],
            ScopeRegistry.GOOGLE_API_SCOPES["drive"]["file"],
            # Gmail basics
            ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["readonly"],
            ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["send"],
            ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["compose"],
            ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["modify"],
            ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["labels"],
            # Gmail settings needed for filters/forwarding
            ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["settings_basic"],
            ScopeRegistry.GOOGLE_API_SCOPES["gmail"]["settings_sharing"]
        ]
        
        return " ".join(default_scopes)
    
    @classmethod
    def get_legacy_chat_app_scopes(cls) -> List[str]:
        """Get Google Chat API scopes for app development."""
        logger.info("COMPATIBILITY: Generating legacy chat app scopes")
        
        try:
            registry = ScopeRegistry()
            return [
                "https://www.googleapis.com/auth/chat.bot",  # Not in registry, use literal
                registry.GOOGLE_API_SCOPES["chat"]["messages"],
                registry.GOOGLE_API_SCOPES["chat"]["spaces"],
                "https://www.googleapis.com/auth/chat.apps",  # Not in registry, use literal
                registry.GOOGLE_API_SCOPES["cloud"]["platform"]
            ]
        except Exception as e:
            logger.warning(f"COMPATIBILITY: Failed to generate chat app scopes from registry: {e}")
            # Fallback to hardcoded scopes
            return [
                'https://www.googleapis.com/auth/chat.bot',
                'https://www.googleapis.com/auth/chat.messages',
                'https://www.googleapis.com/auth/chat.spaces',
                'https://www.googleapis.com/auth/chat.apps',
                'https://www.googleapis.com/auth/cloud-platform'
            ]
    
    @classmethod
    def resolve_legacy_call(cls, source_file: str, scope_request: Any) -> List[str]:
        """
        Automatically resolve legacy scope calls from any source
        
        Args:
            source_file: Source file making the request
            scope_request: The scope request (string, list, or dict)
            
        Returns:
            List of resolved scope URLs
        """
        logger.info(f"COMPATIBILITY: Resolving legacy call from {source_file}: {scope_request}")
        
        try:
            if source_file == "service_manager.py":
                if isinstance(scope_request, str):
                    # Single scope lookup in SCOPE_GROUPS
                    legacy_groups = cls.get_legacy_scope_groups()
                    if scope_request in legacy_groups:
                        return [legacy_groups[scope_request]]
                    else:
                        # Try to resolve through registry
                        return [ScopeRegistry.resolve_legacy_scope(scope_request)]
                elif isinstance(scope_request, list):
                    # Multiple scope lookup
                    legacy_groups = cls.get_legacy_scope_groups()
                    resolved = []
                    for scope in scope_request:
                        if scope in legacy_groups:
                            resolved.append(legacy_groups[scope])
                        else:
                            resolved.append(ScopeRegistry.resolve_legacy_scope(scope))
                    return resolved
            
            elif source_file == "service_helpers.py":
                if isinstance(scope_request, str):
                    # Service default lookup
                    service_defaults = cls.get_legacy_service_defaults()
                    if scope_request in service_defaults:
                        default_scopes = service_defaults[scope_request]["default_scopes"]
                        legacy_groups = cls.get_legacy_scope_groups()
                        resolved = []
                        for scope_name in default_scopes:
                            if scope_name in legacy_groups:
                                resolved.append(legacy_groups[scope_name])
                            else:
                                resolved.append(ScopeRegistry.resolve_legacy_scope(scope_name))
                        return resolved
            
            elif source_file == "settings.py":
                # Return comprehensive drive_scopes
                return cls.get_legacy_drive_scopes()
            
            elif source_file == "fastmcp_oauth_endpoints.py":
                # Return OAuth endpoint scopes
                return cls.get_legacy_oauth_endpoint_scopes()
            
            elif source_file == "dynamic_client_registration.py":
                # Return DCR default scopes
                return cls.get_legacy_dcr_scope_defaults().split()
            
            elif source_file == "google_auth.py":
                # Use the comprehensive OAuth scopes
                return cls.get_legacy_drive_scopes()
            
            # Fallback: try to resolve through registry
            if isinstance(scope_request, str):
                return [ScopeRegistry.resolve_legacy_scope(scope_request)]
            elif isinstance(scope_request, list):
                return [ScopeRegistry.resolve_legacy_scope(scope) for scope in scope_request]
            else:
                logger.warning(f"COMPATIBILITY: Unknown scope request format from {source_file}: {type(scope_request)}")
                return []
        
        except Exception as e:
            logger.error(f"COMPATIBILITY: Error resolving legacy call from {source_file}: {e}")
            return []
    
    @classmethod
    def clear_cache(cls):
        """Clear all cached compatibility data"""
        logger.info("COMPATIBILITY: Clearing all caches")
        cls._legacy_scope_groups_cache = None
        cls._legacy_service_defaults_cache = None
        cls._legacy_drive_scopes_cache = None
        # Force immediate cache invalidation
        logger.info("COMPATIBILITY: Cache cleared - next scope request will regenerate from updated registry")
    
    @classmethod
    def get_cache_stats(cls) -> Dict[str, bool]:
        """Get cache status for debugging"""
        return {
            "scope_groups_cached": cls._legacy_scope_groups_cache is not None,
            "service_defaults_cached": cls._legacy_service_defaults_cache is not None,
            "drive_scopes_cached": cls._legacy_drive_scopes_cache is not None
        }


class MigrationHelper:
    """Helper functions for migrating from legacy scope usage"""
    
    @staticmethod
    def analyze_legacy_usage(file_path: str, content: str) -> Dict[str, Any]:
        """
        Analyze legacy scope usage in a file
        
        Args:
            file_path: Path to the file being analyzed
            content: File content to analyze
            
        Returns:
            Dictionary with analysis results
        """
        logger.info(f"MIGRATION: Analyzing legacy usage in {file_path}")
        
        analysis = {
            "file_path": file_path,
            "legacy_patterns_found": [],
            "scope_references": [],
            "recommended_migration": []
        }
        
        # Look for common legacy patterns
        legacy_patterns = [
            ("SCOPE_GROUPS", "Direct usage of SCOPE_GROUPS dictionary"),
            ("SERVICE_DEFAULTS", "Direct usage of SERVICE_DEFAULTS dictionary"),
            ("drive_scopes", "Direct usage of settings.drive_scopes"),
            ("scopes_supported", "Hardcoded scopes in OAuth endpoints"),
            ("default_scopes", "Hardcoded default scopes in service config")
        ]
        
        for pattern, description in legacy_patterns:
            if pattern in content:
                analysis["legacy_patterns_found"].append({
                    "pattern": pattern,
                    "description": description
                })
        
        # Extract scope references
        import re
        scope_urls = re.findall(r'https://[^\s",\']+googleapis\.com/auth/[^\s",\']+', content)
        scope_names = re.findall(r'["\']([a-z_]+_[a-z_]+)["\']', content)
        
        analysis["scope_references"] = {
            "urls": list(set(scope_urls)),
            "names": list(set(scope_names))
        }
        
        # Provide migration recommendations
        if "service_manager.py" in file_path:
            analysis["recommended_migration"].append(
                "Replace SCOPE_GROUPS with CompatibilityShim.get_legacy_scope_groups()"
            )
        elif "service_helpers.py" in file_path:
            analysis["recommended_migration"].append(
                "Replace SERVICE_DEFAULTS with CompatibilityShim.get_legacy_service_defaults()"
            )
        elif "settings.py" in file_path:
            analysis["recommended_migration"].append(
                "Replace drive_scopes property with CompatibilityShim.get_legacy_drive_scopes()"
            )
        
        return analysis
    
    @staticmethod
    def generate_migration_report(analyses: List[Dict[str, Any]]) -> str:
        """
        Generate a comprehensive migration report
        
        Args:
            analyses: List of file analysis results
            
        Returns:
            Formatted migration report
        """
        report = "# OAuth Scope Migration Report\n\n"
        
        total_files = len(analyses)
        files_with_legacy = sum(1 for a in analyses if a["legacy_patterns_found"])
        
        report += f"## Summary\n"
        report += f"- Total files analyzed: {total_files}\n"
        report += f"- Files with legacy patterns: {files_with_legacy}\n"
        report += f"- Migration completion: {((total_files - files_with_legacy) / total_files * 100):.1f}%\n\n"
        
        for analysis in analyses:
            if analysis["legacy_patterns_found"]:
                report += f"## {analysis['file_path']}\n"
                report += f"**Legacy patterns found:**\n"
                for pattern in analysis["legacy_patterns_found"]:
                    report += f"- {pattern['pattern']}: {pattern['description']}\n"
                
                if analysis["recommended_migration"]:
                    report += f"\n**Recommended migration steps:**\n"
                    for rec in analysis["recommended_migration"]:
                        report += f"- {rec}\n"
                
                report += "\n"
        
        return report