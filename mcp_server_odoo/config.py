"""Configuration management for Odoo MCP Server.

This module handles loading and validation of environment variables
for connecting to Odoo via XML-RPC.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv


@dataclass
class OdooConfig:
    """Configuration for Odoo connection and MCP server settings."""

    # Required fields
    url: str

    # Authentication (one method required)
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

    # Optional fields with defaults
    database: Optional[str] = None
    log_level: str = "INFO"
    default_limit: int = 10
    max_limit: int = 100

    # MCP transport configuration
    transport: Literal["stdio", "streamable-http"] = "stdio"
    host: str = "localhost"
    port: int = 8000

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Validate URL
        if not self.url:
            raise ValueError("ODOO_URL is required")

        # Ensure URL format
        if not self.url.startswith(("http://", "https://")):
            raise ValueError("ODOO_URL must start with http:// or https://")

        # Validate authentication
        has_api_key = bool(self.api_key)
        has_credentials = bool(self.username and self.password)

        if not has_api_key and not has_credentials:
            raise ValueError(
                "Authentication required: provide either ODOO_API_KEY or "
                "both ODOO_USER and ODOO_PASSWORD"
            )

        # Validate numeric fields
        if self.default_limit <= 0:
            raise ValueError("ODOO_MCP_DEFAULT_LIMIT must be positive")

        if self.max_limit <= 0:
            raise ValueError("ODOO_MCP_MAX_LIMIT must be positive")

        if self.default_limit > self.max_limit:
            raise ValueError("ODOO_MCP_DEFAULT_LIMIT cannot exceed ODOO_MCP_MAX_LIMIT")

        # Validate log level
        valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level.upper() not in valid_log_levels:
            raise ValueError(
                f"Invalid log level: {self.log_level}. "
                f"Must be one of: {', '.join(valid_log_levels)}"
            )

        # Validate transport
        valid_transports = {"stdio", "streamable-http"}
        if self.transport not in valid_transports:
            raise ValueError(
                f"Invalid transport: {self.transport}. "
                f"Must be one of: {', '.join(valid_transports)}"
            )

        # Validate port
        if self.port <= 0 or self.port > 65535:
            raise ValueError("Port must be between 1 and 65535")

    @property
    def uses_api_key(self) -> bool:
        """Check if configuration uses API key authentication."""
        return bool(self.api_key)

    @property
    def uses_credentials(self) -> bool:
        """Check if configuration uses username/password authentication."""
        return bool(self.username and self.password)

    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> "OdooConfig":
        """Create configuration from environment variables.

        Args:
            env_file: Optional path to .env file

        Returns:
            OdooConfig: Validated configuration object
        """
        return load_config(env_file)


def load_config(env_file: Optional[Path] = None) -> OdooConfig:
    """Load configuration from environment variables and .env file.

    Args:
        env_file: Optional path to .env file. If not provided,
                 looks for .env in current directory.

    Returns:
        OdooConfig: Validated configuration object

    Raises:
        ValueError: If required configuration is missing or invalid
    """
    # Check if we have a .env file or environment variables
    if env_file:
        if not env_file.exists():
            raise ValueError(
                f"Configuration file not found: {env_file}\n"
                "Please create a .env file based on .env.example"
            )
        load_dotenv(env_file)
    else:
        # Check current directory for .env
        default_env = Path(".env")
        if default_env.exists():
            load_dotenv()
        elif not os.getenv("ODOO_URL"):
            # No .env file and no ODOO_URL in environment
            raise ValueError(
                "No .env file found and ODOO_URL not set in environment.\n"
                "Please create a .env file based on .env.example or set environment variables."
            )

    # Helper function to get int with default
    def get_int_env(key: str, default: int) -> int:
        value = os.getenv(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"{key} must be a valid integer") from None

    # Create configuration
    config = OdooConfig(
        url=os.getenv("ODOO_URL", "").strip(),
        api_key=os.getenv("ODOO_API_KEY", "").strip() or None,
        username=os.getenv("ODOO_USER", "").strip() or None,
        password=os.getenv("ODOO_PASSWORD", "").strip() or None,
        database=os.getenv("ODOO_DB", "").strip() or None,
        log_level=os.getenv("ODOO_MCP_LOG_LEVEL", "INFO").strip(),
        default_limit=get_int_env("ODOO_MCP_DEFAULT_LIMIT", 10),
        max_limit=get_int_env("ODOO_MCP_MAX_LIMIT", 100),
        transport=os.getenv("ODOO_MCP_TRANSPORT", "stdio").strip(),
        host=os.getenv("ODOO_MCP_HOST", "localhost").strip(),
        port=get_int_env("ODOO_MCP_PORT", 8000),
    )

    return config


# Singleton configuration instance
_config: Optional[OdooConfig] = None


def get_config() -> OdooConfig:
    """Get the singleton configuration instance.

    Returns:
        OdooConfig: The configuration object

    Raises:
        ValueError: If configuration is not yet loaded
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: OdooConfig) -> None:
    """Set the singleton configuration instance.

    This is primarily useful for testing.

    Args:
        config: The configuration object to set
    """
    global _config
    _config = config


def reset_config() -> None:
    """Reset the singleton configuration instance.

    This is primarily useful for testing.
    """
    global _config
    _config = None
