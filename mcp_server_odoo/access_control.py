"""Access control for Odoo models via XML-RPC.

This module provides access control functionality that works with both
MCP addon (preferred) and vanilla Odoo installations.
"""

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .config import OdooConfig
from .odoo_connection import OdooConnection

logger = logging.getLogger(__name__)


class AccessControlError(Exception):
    """Exception for access control failures."""

    pass


@dataclass
class ModelPermissions:
    """Permissions for a specific model."""

    model: str
    enabled: bool
    can_read: bool = False
    can_write: bool = False
    can_create: bool = False
    can_unlink: bool = False

    def can_perform(self, operation: str) -> bool:
        """Check if a specific operation is allowed."""
        operation_map = {
            "read": self.can_read,
            "write": self.can_write,
            "create": self.can_create,
            "unlink": self.can_unlink,
            "delete": self.can_unlink,  # Alias
        }
        return operation_map.get(operation, False)


@dataclass
class CacheEntry:
    """Cache entry for permission data."""

    data: Any
    timestamp: datetime

    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if cache entry is expired."""
        return datetime.now() - self.timestamp > timedelta(seconds=ttl_seconds)


class AccessController:
    """Controls access to Odoo models via standard XML-RPC methods.

    This controller can work with both MCP addon (preferred) and vanilla Odoo installations.
    """

    # Cache TTL in seconds
    CACHE_TTL = 300  # 5 minutes

    def __init__(self, config: OdooConfig, cache_ttl: int = CACHE_TTL):
        """Initialize access controller.

        Args:
            config: Odoo configuration
            cache_ttl: Cache TTL in seconds
        """
        self.config = config
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._connection: Optional[OdooConnection] = None
        self._use_mcp_addon = False

    def set_connection(self, connection: OdooConnection) -> None:
        """Set the Odoo connection for access control.

        Args:
            connection: Active Odoo connection
        """
        self._connection = connection
        # Detect if MCP addon is available
        self._detect_mcp_addon()

    def _detect_mcp_addon(self) -> None:
        """Detect if MCP addon is available and working."""
        if not self._connection:
            return

        try:
            # Try to access MCP-specific model
            self._connection.execute_kw("mcp.enabled.model", "search", [[]], {"limit": 1})
            self._use_mcp_addon = True
            logger.info("MCP addon detected - using enhanced access control")
        except Exception as e:
            self._use_mcp_addon = False
            logger.info("MCP addon not available - using basic access control")

    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key in self._cache:
            entry = self._cache[key]
            if not entry.is_expired(self.cache_ttl):
                logger.debug(f"Cache hit for {key}")
                return entry.data
            else:
                logger.debug(f"Cache expired for {key}")
                del self._cache[key]
        return None

    def _set_cache(self, key: str, data: Any) -> None:
        """Set value in cache."""
        self._cache[key] = CacheEntry(data=data, timestamp=datetime.now())
        logger.debug(f"Cached {key}")

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        logger.info("Cleared access control cache")

    def get_enabled_models(self) -> List[Dict[str, str]]:
        """Get list of all accessible models.

        Returns:
            List of dicts with 'model' and 'name' keys

        Raises:
            AccessControlError: If request fails
        """
        cache_key = "enabled_models"

        # Check cache
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        if not self._connection:
            raise AccessControlError("No connection available for access control")

        try:
            if self._use_mcp_addon:
                # Use MCP addon if available
                return self._get_enabled_models_mcp()
            else:
                # Fallback to basic model discovery
                return self._get_enabled_models_basic()
        except Exception as e:
            logger.error(f"Failed to get enabled models: {e}")
            # Return empty list as fallback
            return []

    def _get_enabled_models_mcp(self) -> List[Dict[str, str]]:
        """Get enabled models using MCP addon."""
        if not self._connection:
            return []
            
        enabled_records = self._connection.execute_kw(
            "mcp.enabled.model", 
            "search_read", 
            [[("active", "=", True)]], 
            {"fields": ["model_id"]}
        )
        
        models = []
        for record in enabled_records:
            model_id = record.get("model_id")
            if model_id:
                # Get model details
                model_info = self._connection.execute_kw(
                    "ir.model", 
                    "read", 
                    [[model_id]], 
                    {"fields": ["model", "name"]}
                )
                if model_info:
                    models.append({
                        "model": model_info[0].get("model", ""),
                        "name": model_info[0].get("name", "")
                    })
        
        return models

    def _get_enabled_models_basic(self) -> List[Dict[str, str]]:
        """Get accessible models using basic Odoo methods."""
        if not self._connection:
            return []
            
        # Get all models that the user can access
        model_ids = self._connection.execute_kw(
            "ir.model", 
            "search", 
            [[("transient", "=", False)]], 
            {"limit": 1000}  # Reasonable limit
        )
        
        models = []
        for model_id in model_ids:
            try:
                model_info = self._connection.execute_kw(
                    "ir.model", 
                    "read", 
                    [[model_id]], 
                    {"fields": ["model", "name"]}
                )
                if model_info:
                    model_name = model_info[0].get("model", "")
                    # Skip system models and private models
                    if not model_name.startswith("_") and not model_name.startswith("ir."):
                        models.append({
                            "model": model_name,
                            "name": model_info[0].get("name", model_name)
                        })
            except Exception as e:
                logger.debug(f"Could not access model {model_id}: {e}")
                continue
        
        return models

    def is_model_enabled(self, model: str) -> bool:
        """Check if a model is accessible.

        Args:
            model: The Odoo model name (e.g., 'res.partner')

        Returns:
            True if model is accessible, False otherwise
        """
        try:
            if self._use_mcp_addon:
                # Check MCP enabled models
                enabled_models = self.get_enabled_models()
                return any(m["model"] == model for m in enabled_models)
            else:
                # Basic check - try to access the model
                return self._check_model_access_basic(model)
        except Exception as e:
            logger.error(f"Failed to check if model {model} is enabled: {e}")
            return False

    def _check_model_access_basic(self, model: str) -> bool:
        """Basic model access check using standard Odoo methods."""
        if not self._connection:
            return False

        try:
            # Try to get field definitions - if this works, the model is accessible
            self._connection.fields_get(model)
            return True
        except Exception:
            return False

    def get_model_permissions(self, model: str) -> ModelPermissions:
        """Get permissions for a specific model.

        Args:
            model: The Odoo model name

        Returns:
            ModelPermissions object with permission details

        Raises:
            AccessControlError: If request fails
        """
        cache_key = f"permissions_{model}"

        # Check cache
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        if not self._connection:
            raise AccessControlError("No connection available for access control")

        try:
            if self._use_mcp_addon:
                # Use MCP addon permissions
                permissions = self._get_model_permissions_mcp(model)
            else:
                # Use basic permission checking
                permissions = self._get_model_permissions_basic(model)

            # Cache result
            self._set_cache(cache_key, permissions)

            logger.debug(f"Retrieved permissions for {model}: {permissions}")
            return permissions

        except Exception as e:
            logger.error(f"Failed to get permissions for {model}: {e}")
            # Return default permissions as fallback
            return ModelPermissions(
                model=model,
                enabled=True,
                can_read=True,
                can_write=True,
                can_create=True,
                can_unlink=True
            )

    def _get_model_permissions_mcp(self, model: str) -> ModelPermissions:
        """Get model permissions using MCP addon."""
        if not self._connection:
            return ModelPermissions(model=model, enabled=False)
            
        # Find the model record
        model_ids = self._connection.execute_kw(
            "ir.model", 
            "search", 
            [[("model", "=", model)]], 
            {"limit": 1}
        )
        
        if not model_ids:
            return ModelPermissions(model=model, enabled=False)

        # Get MCP enabled model record
        enabled_ids = self._connection.execute_kw(
            "mcp.enabled.model", 
            "search", 
            [[("model_id", "=", model_ids[0])]], 
            {"limit": 1}
        )
        
        if not enabled_ids:
            return ModelPermissions(model=model, enabled=False)

        # Get permissions
        enabled_record = self._connection.execute_kw(
            "mcp.enabled.model", 
            "read", 
            [enabled_ids], 
            {"fields": ["allow_read", "allow_write", "allow_create", "allow_unlink"]}
        )
        
        if not enabled_record:
            return ModelPermissions(model=model, enabled=False)

        record = enabled_record[0]
        return ModelPermissions(
            model=model,
            enabled=True,
            can_read=record.get("allow_read", False),
            can_write=record.get("allow_write", False),
            can_create=record.get("allow_create", False),
            can_unlink=record.get("allow_unlink", False)
        )

    def _get_model_permissions_basic(self, model: str) -> ModelPermissions:
        """Get basic model permissions using standard Odoo methods."""
        if not self._connection:
            return ModelPermissions(model=model, enabled=False)
            
        # For basic access control, we assume all accessible models have full permissions
        # This is a simplified approach - in production you might want more granular control
        try:
            # Test if we can access the model
            self._connection.fields_get(model)
            return ModelPermissions(
                model=model,
                enabled=True,
                can_read=True,
                can_write=True,
                can_create=True,
                can_unlink=True
            )
        except Exception:
            return ModelPermissions(model=model, enabled=False)

    def check_operation_allowed(self, model: str, operation: str) -> Tuple[bool, Optional[str]]:
        """Check if an operation is allowed on a model.

        Args:
            model: The Odoo model name
            operation: The operation to check (read, write, create, unlink)

        Returns:
            Tuple of (allowed, error_message)
        """
        try:
            # Get model permissions
            permissions = self.get_model_permissions(model)

            # Check if model is enabled
            if not permissions.enabled:
                return False, f"Model '{model}' is not enabled for MCP access"

            # Check specific operation
            if not permissions.can_perform(operation):
                return False, f"Operation '{operation}' not allowed on model '{model}'"

            return True, None

        except AccessControlError as e:
            logger.error(f"Access control check failed: {e}")
            return False, str(e)

    def validate_model_access(self, model: str, operation: str) -> None:
        """Validate model access, raising exception if denied.

        Args:
            model: The Odoo model name
            operation: The operation to perform

        Raises:
            AccessControlError: If access is denied
        """
        allowed, error_msg = self.check_operation_allowed(model, operation)
        if not allowed:
            raise AccessControlError(error_msg or f"Access denied to {model}.{operation}")

    def filter_enabled_models(self, models: List[str]) -> List[str]:
        """Filter list of models to only include enabled ones.

        Args:
            models: List of model names to filter

        Returns:
            List of enabled model names
        """
        try:
            enabled_models = self.get_enabled_models()
            enabled_set = {m["model"] for m in enabled_models}
            return [m for m in models if m in enabled_set]
        except AccessControlError as e:
            logger.error(f"Failed to filter models: {e}")
            return []

    def get_all_permissions(self) -> Dict[str, ModelPermissions]:
        """Get permissions for all enabled models.

        Returns:
            Dict mapping model names to their permissions
        """
        permissions = {}

        try:
            enabled_models = self.get_enabled_models()

            for model_info in enabled_models:
                model = model_info["model"]
                try:
                    permissions[model] = self.get_model_permissions(model)
                except AccessControlError as e:
                    logger.warning(f"Failed to get permissions for {model}: {e}")

        except AccessControlError as e:
            logger.error(f"Failed to get all permissions: {e}")

        return permissions
