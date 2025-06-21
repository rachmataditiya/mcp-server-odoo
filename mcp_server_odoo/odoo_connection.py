"""Odoo XML-RPC connection management.

This module provides the OdooConnection class for managing connections
to Odoo via XML-RPC using MCP-specific endpoints.
"""

import json
import logging
import socket
import urllib.error
import urllib.request
import xmlrpc.client
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

from .config import OdooConfig
from .error_sanitizer import ErrorSanitizer
from .performance import PerformanceManager

logger = logging.getLogger(__name__)


class OdooConnectionError(Exception):
    """Base exception for Odoo connection errors."""

    pass


class OdooConnection:
    """Manages XML-RPC connections to Odoo with MCP-specific endpoints.

    This class provides connection management, health checking, and
    proper resource cleanup for Odoo XML-RPC connections.
    """

    # MCP-specific endpoints (preferred)
    MCP_DB_ENDPOINT = "/mcp/xmlrpc/db"
    MCP_COMMON_ENDPOINT = "/mcp/xmlrpc/common"
    MCP_OBJECT_ENDPOINT = "/mcp/xmlrpc/object"
    
    # Standard Odoo endpoints (fallback)
    STANDARD_DB_ENDPOINT = "/xmlrpc/2/db"
    STANDARD_COMMON_ENDPOINT = "/xmlrpc/2/common"
    STANDARD_OBJECT_ENDPOINT = "/xmlrpc/2/object"
    
    # Alternative endpoints (some Odoo installations use these)
    ALT_DB_ENDPOINT = "/xmlrpc/db"
    ALT_COMMON_ENDPOINT = "/xmlrpc/common"
    ALT_OBJECT_ENDPOINT = "/xmlrpc/object"
    
    # Legacy endpoints (older Odoo versions)
    LEGACY_DB_ENDPOINT = "/xmlrpc/1/db"
    LEGACY_COMMON_ENDPOINT = "/xmlrpc/1/common"
    LEGACY_OBJECT_ENDPOINT = "/xmlrpc/1/object"

    # Connection timeout in seconds
    DEFAULT_TIMEOUT = 30

    def __init__(
        self,
        config: OdooConfig,
        timeout: int = DEFAULT_TIMEOUT,
        performance_manager: Optional[PerformanceManager] = None,
    ):
        """Initialize connection with configuration.

        Args:
            config: OdooConfig object with connection parameters
            timeout: Connection timeout in seconds
            performance_manager: Optional performance manager for optimizations
        """
        self.config = config
        self.timeout = timeout
        self._url_components = self._parse_url(config.url)

        # Performance manager for optimizations
        self._performance_manager = performance_manager or PerformanceManager(config)

        # XML-RPC proxies (created on connect)
        self._db_proxy: Optional[xmlrpc.client.ServerProxy] = None
        self._common_proxy: Optional[xmlrpc.client.ServerProxy] = None
        self._object_proxy: Optional[xmlrpc.client.ServerProxy] = None

        # Connection state
        self._connected = False
        self._uid: Optional[int] = None
        self._database: Optional[str] = None
        self._authenticated = False
        self._auth_method: Optional[str] = None  # 'api_key' or 'password'

        logger.info(f"Initialized OdooConnection for {self._url_components['host']}")

    def _parse_url(self, url: str) -> Dict[str, Any]:
        """Parse and validate Odoo URL.

        Args:
            url: The Odoo server URL

        Returns:
            Dictionary with URL components

        Raises:
            OdooConnectionError: If URL is invalid
        """
        try:
            parsed = urlparse(url)

            if parsed.scheme not in ("http", "https"):
                raise OdooConnectionError(
                    f"Invalid URL scheme: {parsed.scheme}. Must be http or https"
                )

            if not parsed.hostname:
                raise OdooConnectionError("Invalid URL: missing hostname")

            port = parsed.port
            if not port:
                port = 443 if parsed.scheme == "https" else 80

            # Build base URL without any path components
            base_url = f"{parsed.scheme}://{parsed.hostname}"
            if port not in (80, 443):
                base_url += f":{port}"

            return {
                "scheme": parsed.scheme,
                "host": parsed.hostname,
                "port": port,
                "path": parsed.path.rstrip("/") or "",
                "base_url": base_url,
            }

        except Exception as e:
            raise OdooConnectionError(f"Failed to parse URL: {e}") from e

    def _create_transport(self) -> xmlrpc.client.Transport:
        """Create XML-RPC transport with timeout support.

        Returns:
            Configured Transport object
        """

        class TimeoutTransport(xmlrpc.client.Transport):
            def __init__(self, timeout, *args, **kwargs):
                self.timeout = timeout
                super().__init__(*args, **kwargs)

            def make_connection(self, host):
                connection = super().make_connection(host)
                if hasattr(connection, "sock") and connection.sock:
                    connection.sock.settimeout(self.timeout)
                return connection

        return TimeoutTransport(self.timeout)

    def _create_transport_with_redirects(self) -> xmlrpc.client.Transport:
        """Create XML-RPC transport with timeout support and redirect handling.
        
        Returns:
            Transport object with timeout and redirect support
        """
        class RedirectTransport(xmlrpc.client.Transport):
            def __init__(self, timeout, *args, **kwargs):
                self.timeout = timeout
                super().__init__(*args, **kwargs)

            def make_connection(self, host):
                connection = super().make_connection(host)
                if hasattr(connection, "sock") and connection.sock:
                    connection.sock.settimeout(self.timeout)
                return connection

            def request(self, host, handler, request_body, verbose=0):
                """Override request to handle redirects and SSL issues."""
                import http.client
                import urllib.parse
                import ssl
                
                # Parse the URL
                parsed = urllib.parse.urlparse(handler)
                
                # Create context for SSL
                if parsed.scheme == 'https':
                    # Create SSL context that ignores certificate verification
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    conn = http.client.HTTPSConnection(parsed.netloc, timeout=self.timeout, context=context)
                else:
                    conn = http.client.HTTPConnection(parsed.netloc, timeout=self.timeout)
                
                # Set headers
                headers = {
                    'Content-Type': 'text/xml',
                    'User-Agent': 'Odoo MCP Server',
                    'Host': parsed.netloc,
                }
                
                try:
                    # Make the request
                    conn.request('POST', parsed.path, request_body, headers)
                    response = conn.getresponse()
                    
                    # Handle redirects
                    if response.status in (301, 302, 307, 308):
                        location = response.getheader('Location')
                        if location:
                            # Follow the redirect
                            conn.close()
                            return self.request(host, location, request_body, verbose)
                    
                    # Read response
                    data = response.read()
                    conn.close()
                    
                    # Return response in expected format
                    return response.status, response.reason, data
                    
                except Exception as e:
                    conn.close()
                    raise e

        return RedirectTransport(self.timeout)

    def _build_endpoint_url(self, endpoint: str) -> str:
        """Build full URL for an MCP endpoint.

        Args:
            endpoint: The MCP endpoint path

        Returns:
            Full URL for the endpoint
        """
        return f"{self._url_components['base_url']}{endpoint}"

    def _detect_available_endpoints(self) -> Dict[str, str]:
        """Detect which endpoints are available on the Odoo server.
        
        Returns:
            Dictionary mapping endpoint types to their URLs
        """
        endpoints = {}
        
        # Define endpoint sets to try in order of preference
        endpoint_sets = [
            # MCP endpoints (preferred)
            {
                'name': 'MCP',
                'db': self.MCP_DB_ENDPOINT,
                'common': self.MCP_COMMON_ENDPOINT,
                'object': self.MCP_OBJECT_ENDPOINT
            },
            # Standard Odoo endpoints
            {
                'name': 'Standard',
                'db': self.STANDARD_DB_ENDPOINT,
                'common': self.STANDARD_COMMON_ENDPOINT,
                'object': self.STANDARD_OBJECT_ENDPOINT
            },
            # Alternative endpoints
            {
                'name': 'Alternative',
                'db': self.ALT_DB_ENDPOINT,
                'common': self.ALT_COMMON_ENDPOINT,
                'object': self.ALT_OBJECT_ENDPOINT
            },
            # Legacy endpoints
            {
                'name': 'Legacy',
                'db': self.LEGACY_DB_ENDPOINT,
                'common': self.LEGACY_COMMON_ENDPOINT,
                'object': self.LEGACY_OBJECT_ENDPOINT
            }
        ]
        
        logger.info(f"Starting endpoint detection for {self._url_components['base_url']}")
        
        # Try with current URL scheme first
        for endpoint_set in endpoint_sets:
            try:
                endpoint_url = self._build_endpoint_url(endpoint_set['common'])
                logger.info(f"Trying {endpoint_set['name']} endpoint: {endpoint_url}")
                
                # Test common endpoint
                test_proxy = xmlrpc.client.ServerProxy(
                    endpoint_url,
                    transport=self._create_transport_with_redirects()
                )
                
                # Try to get version
                version = test_proxy.version()
                
                # If we get here, this endpoint set works
                endpoints['db'] = endpoint_set['db']
                endpoints['common'] = endpoint_set['common']
                endpoints['object'] = endpoint_set['object']
                
                logger.info(f"Successfully connected using {endpoint_set['name']} endpoints")
                logger.info(f"Server version: {version}")
                return endpoints
                
            except Exception as e:
                logger.warning(f"{endpoint_set['name']} endpoints failed: {type(e).__name__}: {e}")
                continue
        
        # If HTTP failed, try HTTPS
        if self._url_components['scheme'] == 'http':
            logger.info("HTTP failed, trying HTTPS...")
            original_scheme = self._url_components['scheme']
            original_base_url = self._url_components['base_url']
            
            # Temporarily switch to HTTPS
            self._url_components['scheme'] = 'https'
            self._url_components['base_url'] = self._url_components['base_url'].replace('http://', 'https://')
            
            try:
                for endpoint_set in endpoint_sets:
                    try:
                        endpoint_url = self._build_endpoint_url(endpoint_set['common'])
                        logger.info(f"Trying {endpoint_set['name']} HTTPS endpoint: {endpoint_url}")
                        
                        test_proxy = xmlrpc.client.ServerProxy(
                            endpoint_url,
                            transport=self._create_transport_with_redirects()
                        )
                        
                        version = test_proxy.version()
                        
                        endpoints['db'] = endpoint_set['db']
                        endpoints['common'] = endpoint_set['common']
                        endpoints['object'] = endpoint_set['object']
                        
                        logger.info(f"Successfully connected using {endpoint_set['name']} HTTPS endpoints")
                        logger.info(f"Server version: {version}")
                        return endpoints
                        
                    except Exception as e:
                        logger.warning(f"{endpoint_set['name']} HTTPS endpoints failed: {type(e).__name__}: {e}")
                        continue
            finally:
                # Restore original scheme
                self._url_components['scheme'] = original_scheme
                self._url_components['base_url'] = original_base_url
        
        # If we get here, no endpoints worked
        logger.error("No available XML-RPC endpoints found on Odoo server")
        logger.error(f"Tried URL: {self._url_components['base_url']}")
        logger.error("Please check:")
        logger.error("1. Odoo server is running and accessible")
        logger.error("2. XML-RPC is enabled in Odoo configuration")
        logger.error("3. Network connectivity and firewall settings")
        logger.error("4. URL is correct and includes proper scheme (http/https)")
        raise OdooConnectionError("No available XML-RPC endpoints found on Odoo server")

    def connect(self) -> None:
        """Establish connection to Odoo server.

        Creates XML-RPC proxies for available endpoints but doesn't
        authenticate yet. Uses connection pooling for better performance.

        Raises:
            OdooConnectionError: If connection fails
        """
        if self._connected:
            logger.warning("Already connected to Odoo")
            return

        try:
            # Detect available endpoints
            available_endpoints = self._detect_available_endpoints()
            
            # Use connection pool for proxies
            self._db_proxy = self._performance_manager.get_optimized_connection(
                available_endpoints['db']
            )
            self._common_proxy = self._performance_manager.get_optimized_connection(
                available_endpoints['common']
            )
            self._object_proxy = self._performance_manager.get_optimized_connection(
                available_endpoints['object']
            )

            # Test connection by calling server_version
            self._test_connection()

            self._connected = True
            logger.info("Successfully connected to Odoo server")

        except socket.timeout:
            raise OdooConnectionError(f"Connection timeout after {self.timeout} seconds") from None
        except socket.error as e:
            raise OdooConnectionError(
                f"Failed to connect to {self._url_components['host']}:"
                f"{self._url_components['port']}: {e}"
            ) from e
        except Exception as e:
            raise OdooConnectionError(f"Connection failed: {e}") from e

    def _test_connection(self) -> None:
        """Test connection by calling server_version.

        Raises:
            OdooConnectionError: If test fails
        """
        try:
            # Try to get server version via common endpoint
            if self._common_proxy is not None:
                version = self._common_proxy.version()
                logger.debug(f"Server version: {version}")
            else:
                raise OdooConnectionError("Common proxy not initialized")
        except Exception as e:
            raise OdooConnectionError(f"Connection test failed: {e}") from e

    def disconnect(self, suppress_logging: bool = False) -> None:
        """Close connection and cleanup resources."""
        if not self._connected:
            if not suppress_logging:
                try:
                    logger.warning("Not connected to Odoo")
                except (ValueError, RuntimeError):
                    # Ignore logging errors during cleanup
                    pass
            return

        # Clear proxies (but don't close pooled connections)
        self._db_proxy = None
        self._common_proxy = None
        self._object_proxy = None

        # Clear connection state
        self._connected = False
        self._uid = None
        self._database = None
        self._authenticated = False
        self._auth_method = None

        if not suppress_logging:
            try:
                logger.info("Disconnected from Odoo server")
            except (ValueError, RuntimeError):
                # Ignore logging errors during cleanup
                pass

    def check_health(self) -> Tuple[bool, str]:
        """Check connection health.

        Returns:
            Tuple of (is_healthy, status_message)
        """
        if not self._connected:
            return False, "Not connected"

        try:
            # Try to get server version as health check
            if self._common_proxy is not None:
                version = self._common_proxy.version()
                if isinstance(version, dict):
                    server_version = version.get('server_version', 'unknown')
                else:
                    server_version = 'unknown'
                return True, f"Connected to Odoo {server_version}"
            else:
                return False, "Common proxy not available"
        except socket.timeout:
            return False, f"Health check timeout after {self.timeout} seconds"
        except Exception as e:
            return False, f"Health check failed: {e}"

    def test_connection(self) -> bool:
        """Test if connection to Odoo is working.

        Returns:
            True if connection is working, False otherwise
        """
        # If not connected, try to connect first
        if not self._connected:
            try:
                self.connect()
            except Exception as e:
                logger.error(f"Failed to connect: {e}")
                return False

        # Check health
        is_healthy, _ = self.check_health()
        return is_healthy

    def close(self) -> None:
        """Close the connection (alias for disconnect)."""
        self.disconnect()

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._connected

    @property
    def db_proxy(self) -> xmlrpc.client.ServerProxy:
        """Get database operations proxy.

        Returns:
            XML-RPC proxy for database operations

        Raises:
            OdooConnectionError: If not connected
        """
        if not self._connected or not self._db_proxy:
            raise OdooConnectionError("Not connected to Odoo")
        return self._db_proxy

    @property
    def common_proxy(self) -> xmlrpc.client.ServerProxy:
        """Get common operations proxy.

        Returns:
            XML-RPC proxy for common operations

        Raises:
            OdooConnectionError: If not connected
        """
        if not self._connected or not self._common_proxy:
            raise OdooConnectionError("Not connected to Odoo")
        return self._common_proxy

    @property
    def object_proxy(self) -> xmlrpc.client.ServerProxy:
        """Get object operations proxy.

        Returns:
            XML-RPC proxy for object operations

        Raises:
            OdooConnectionError: If not connected
        """
        if not self._connected or not self._object_proxy:
            raise OdooConnectionError("Not connected to Odoo")
        return self._object_proxy

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False

    def __del__(self):
        """Cleanup on deletion."""
        try:
            # Only disconnect if we're actually connected
            if hasattr(self, "_connected") and self._connected:
                # Suppress logging during cleanup to avoid I/O errors
                self.disconnect(suppress_logging=True)
        except (ValueError, AttributeError, RuntimeError):
            # ValueError: I/O operation on closed file
            # AttributeError: object might be partially initialized
            # RuntimeError: various cleanup-related errors
            pass

    def list_databases(self) -> List[str]:
        """List all available databases on the Odoo server.

        Returns:
            List of database names

        Raises:
            OdooConnectionError: If listing fails
        """
        if not self._connected:
            raise OdooConnectionError("Not connected to Odoo")

        try:
            # Call list_db method on database proxy
            result = self.db_proxy.list()
            # Handle XML-RPC return value which could be various types
            if isinstance(result, (list, tuple)):
                databases = [str(db) for db in result]
            elif result is None:
                databases = []
            else:
                # Single value case
                databases = [str(result)]
            logger.info(f"Found {len(databases)} databases: {databases}")
            return databases
        except Exception as e:
            logger.error(f"Failed to list databases: {e}")
            raise OdooConnectionError(f"Failed to list databases: {e}") from e

    def database_exists(self, db_name: str) -> bool:
        """Check if a specific database exists.

        Args:
            db_name: Name of the database to check

        Returns:
            True if database exists, False otherwise

        Raises:
            OdooConnectionError: If check fails
        """
        try:
            databases = self.list_databases()
            return db_name in databases
        except Exception as e:
            logger.error(f"Failed to check database existence: {e}")
            raise OdooConnectionError(f"Failed to check database existence: {e}") from e

    def auto_select_database(self) -> str:
        """Automatically select an appropriate database.

        Selection logic:
        1. If config.database is set, validate and use it
        2. If only one database exists, use it
        3. If multiple databases exist and one is named 'odoo', use it
        4. Otherwise raise an error

        Returns:
            Selected database name

        Raises:
            OdooConnectionError: If no suitable database can be selected
        """
        # If database is explicitly configured, use it without validation
        # Database listing may be restricted for security reasons
        if self.config.database:
            db_name = self.config.database
            logger.info(f"Using configured database: {db_name}")
            # Skip existence check as database listing might be restricted
            return db_name

        # List available databases
        try:
            databases = self.list_databases()
        except Exception as e:
            # If database listing is restricted, we cannot auto-select
            logger.warning(f"Cannot list databases (may be restricted): {e}")
            raise OdooConnectionError(
                "Database auto-selection failed. Database listing may be restricted. "
                "Please specify ODOO_DB in your configuration."
            ) from e

        # Handle different scenarios
        if not databases:
            raise OdooConnectionError("No databases found on Odoo server")

        if len(databases) == 1:
            db_name = databases[0]
            logger.info(f"Auto-selected only available database: {db_name}")
            return db_name

        # Multiple databases - check for 'odoo'
        if "odoo" in databases:
            logger.info("Auto-selected 'odoo' database from multiple options")
            return "odoo"

        # Cannot auto-select
        raise OdooConnectionError(
            f"Cannot auto-select database. Found {len(databases)} databases: "
            f"{', '.join(databases)}. Please specify ODOO_DB in configuration."
        )

    def validate_database_access(self, db_name: str) -> bool:
        """Validate that we can access the specified database.

        This method attempts to authenticate with the database to verify access.

        Args:
            db_name: Name of the database to validate

        Returns:
            True if database is accessible, False otherwise

        Raises:
            OdooConnectionError: If validation fails
        """
        if not self._connected:
            raise OdooConnectionError("Not connected to Odoo")

        try:
            # For API key auth, we'll need to implement a different check
            # For now, we just verify the database exists
            if self.config.uses_api_key:
                # API key validation would be done during actual authentication
                return self.database_exists(db_name)

            # For username/password auth, try to authenticate
            if self.config.uses_credentials:
                # Try to authenticate with the database
                # This will fail if we don't have access
                uid = self.common_proxy.authenticate(
                    db_name, self.config.username, self.config.password, {}
                )
                if uid:
                    logger.info(f"Successfully validated access to database '{db_name}'")
                    return True
                else:
                    logger.warning(f"Authentication failed for database '{db_name}'")
                    return False

            # Should not reach here due to config validation
            raise OdooConnectionError("No authentication method configured")

        except xmlrpc.client.Fault as e:
            logger.error(f"XML-RPC fault validating database access: {e}")
            if "Access Denied" in str(e):
                return False
            raise OdooConnectionError(f"Failed to validate database access: {e}") from e
        except Exception as e:
            logger.error(f"Error validating database access: {e}")
            raise OdooConnectionError(f"Failed to validate database access: {e}") from e

    def _authenticate_api_key(self, database: str) -> bool:
        """Authenticate using API key.

        Args:
            database: Database name to authenticate against

        Returns:
            True if authentication successful, False otherwise

        Raises:
            OdooConnectionError: If API request fails
        """
        if not self.config.api_key:
            return False

        try:
            # Build URL for API key validation endpoint
            url = f"{self._url_components['base_url']}/mcp/auth/validate"

            # Create request with API key header
            req = urllib.request.Request(url)
            req.add_header("X-API-Key", self.config.api_key)

            # Make the request
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))

                if data.get("success") and data.get("data", {}).get("valid"):
                    self._uid = data["data"].get("user_id")
                    self._database = database
                    self._auth_method = "api_key"
                    self._authenticated = True
                    logger.info(f"Successfully authenticated with API key for user ID {self._uid}")
                    return True
                else:
                    logger.warning("API key validation failed")
                    return False

        except urllib.error.HTTPError as e:
            if e.code == 401:
                logger.warning("Invalid API key")
                return False
            elif e.code == 429:
                logger.warning("Rate limit exceeded during API key validation")
                # For testing, we'll treat rate limit as a temporary failure
                # and fall back to password auth
                return False
            else:
                logger.error(f"HTTP error during API key validation: {e}")
                raise OdooConnectionError(f"Failed to validate API key: {e}") from e
        except Exception as e:
            logger.error(f"Error during API key validation: {e}")
            raise OdooConnectionError(f"Failed to validate API key: {e}") from e

    def _authenticate_password(self, database: str) -> bool:
        """Authenticate using username and password.

        Args:
            database: Database name to authenticate against

        Returns:
            True if authentication successful, False otherwise

        Raises:
            OdooConnectionError: If authentication fails
        """
        if not self.config.username or not self.config.password:
            return False

        try:
            # Use common proxy to authenticate
            # According to Odoo documentation: authenticate(db, username, password, user_agent_env)
            result = self.common_proxy.authenticate(
                database, self.config.username, self.config.password, {}
            )

            # Odoo authenticate returns user ID as int or False
            if result and isinstance(result, (int, float)):
                uid = int(result)  # Ensure it's an integer
                self._uid = uid
                self._database = database
                self._auth_method = "password"
                self._authenticated = True
                logger.info(f"Successfully authenticated with username/password for user ID {uid}")
                return True
            else:
                logger.warning("Username/password authentication failed")
                return False

        except xmlrpc.client.Fault as e:
            # Handle specific Odoo authentication errors
            if "Access Denied" in str(e) or "Invalid credentials" in str(e):
                logger.warning("Invalid username or password")
                return False
            elif "Database not found" in str(e):
                logger.warning(f"Database '{database}' not found")
                return False
            elif "User not found" in str(e):
                logger.warning(f"User '{self.config.username}' not found in database '{database}'")
                return False
            else:
                logger.error(f"Authentication fault: {e}")
                return False
        except Exception as e:
            logger.error(f"Error during password authentication: {e}")
            raise OdooConnectionError(f"Failed to authenticate: {e}") from e

    def authenticate(self, database: Optional[str] = None) -> None:
        """Authenticate with Odoo using available credentials.

        Tries API key authentication first, then falls back to username/password.

        Args:
            database: Database name. If not provided, uses auto-selection.

        Raises:
            OdooConnectionError: If authentication fails
        """
        if not self._connected:
            raise OdooConnectionError("Not connected to Odoo")

        # Get database name
        if database:
            db_name = database
        else:
            db_name = self.auto_select_database()

        # Try API key authentication first
        if self.config.uses_api_key:
            logger.info("Attempting API key authentication")
            if self._authenticate_api_key(db_name):
                return
            else:
                logger.info("API key authentication failed, trying username/password")

        # Try username/password authentication
        if self.config.uses_credentials:
            logger.info("Attempting username/password authentication")
            if self._authenticate_password(db_name):
                return

        # Authentication failed
        raise OdooConnectionError("Authentication failed. Please check your credentials.")

    def is_authenticated(self) -> bool:
        """Check if currently authenticated."""
        return self._authenticated

    @property
    def uid(self) -> Optional[int]:
        """Get authenticated user ID."""
        return self._uid

    @property
    def database(self) -> Optional[str]:
        """Get authenticated database name."""
        return self._database

    @property
    def auth_method(self) -> Optional[str]:
        """Get authentication method used ('api_key' or 'password')."""
        return self._auth_method

    @property
    def performance_manager(self) -> PerformanceManager:
        """Get the performance manager instance."""
        return self._performance_manager

    def execute(self, model: str, method: str, *args) -> Any:
        """Execute an operation on an Odoo model.

        This is a simplified interface that calls execute_kw with empty kwargs.

        Args:
            model: The Odoo model name (e.g., 'res.partner')
            method: The method to call (e.g., 'search', 'read')
            *args: Arguments to pass to the method

        Returns:
            The result from Odoo

        Raises:
            OdooConnectionError: If not authenticated or execution fails
        """
        return self.execute_kw(model, method, list(args), {})

    def execute_kw(self, model: str, method: str, args: List[Any], kwargs: Dict[str, Any]) -> Any:
        """Execute an operation on an Odoo model with keyword arguments.

        This is the main method for interacting with Odoo models via XML-RPC.

        Args:
            model: The Odoo model name (e.g., 'res.partner')
            method: The method to call (e.g., 'search_read')
            args: List of positional arguments for the method
            kwargs: Dictionary of keyword arguments for the method

        Returns:
            The result from Odoo

        Raises:
            OdooConnectionError: If not authenticated or execution fails
        """
        if not self._authenticated:
            raise OdooConnectionError("Not authenticated. Call authenticate() first.")

        if not self._connected:
            raise OdooConnectionError("Not connected to Odoo")

        # Get the appropriate password/token based on auth method
        password_or_token = (
            self.config.api_key if self._auth_method == "api_key" else self.config.password
        )

        try:
            # Log the operation
            logger.debug(f"Executing {method} on {model} with args={args}, kwargs={kwargs}")

            # Execute via object proxy
            result = self.object_proxy.execute_kw(
                self._database, self._uid, password_or_token, model, method, args, kwargs
            )

            logger.debug("Operation completed successfully")
            return result

        except xmlrpc.client.Fault as e:
            logger.error(f"XML-RPC fault during {method} on {model}: {e}")
            # Sanitize the fault string before exposing to user
            sanitized_message = ErrorSanitizer.sanitize_xmlrpc_fault(e.faultString)
            raise OdooConnectionError(f"Operation failed: {sanitized_message}") from e
        except socket.timeout:
            logger.error(f"Timeout during {method} on {model}")
            raise OdooConnectionError(f"Operation timeout after {self.timeout} seconds") from None
        except Exception as e:
            logger.error(f"Error during {method} on {model}: {e}")
            # Sanitize generic errors as well
            sanitized_message = ErrorSanitizer.sanitize_message(str(e))
            raise OdooConnectionError(f"Operation failed: {sanitized_message}") from e

    def search(self, model: str, domain: List[Union[str, List[Any]]], **kwargs) -> List[int]:
        """Search for records matching a domain.

        Args:
            model: The Odoo model name
            domain: Odoo domain filter (e.g., [['is_company', '=', True]])
            **kwargs: Additional parameters (limit, offset, order)

        Returns:
            List of record IDs matching the domain
        """
        return self.execute_kw(model, "search", [domain], kwargs)

    def read(
        self, model: str, ids: List[int], fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Read records by IDs.

        Args:
            model: The Odoo model name
            ids: List of record IDs to read
            fields: List of field names to read (None for all fields)

        Returns:
            List of dictionaries containing record data
        """
        # Try to get cached records
        cached_records = []
        uncached_ids = []

        for record_id in ids:
            cached = self._performance_manager.get_cached_record(model, record_id, fields)
            if cached:
                cached_records.append(cached)
            else:
                uncached_ids.append(record_id)

        # If all records are cached, return them
        if not uncached_ids:
            logger.debug(f"All {len(ids)} records retrieved from cache")
            return cached_records

        # Read uncached records
        kwargs = {}
        if fields:
            kwargs["fields"] = fields

        with self._performance_manager.monitor.track_operation(f"read_{model}"):
            new_records = self.execute_kw(model, "read", [uncached_ids], kwargs)

        # Cache the new records
        for record in new_records:
            self._performance_manager.cache_record(model, record, fields)

        # Combine cached and new records in original order
        all_records = cached_records + new_records
        # Sort by the original ID order
        id_order = {id_val: idx for idx, id_val in enumerate(ids)}
        all_records.sort(key=lambda r: id_order.get(r.get("id", 0), len(ids)))

        return all_records

    def search_read(
        self,
        model: str,
        domain: List[Union[str, List[Any]]],
        fields: Optional[List[str]] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Search for records and read their data in one operation.

        Args:
            model: The Odoo model name
            domain: Odoo domain filter
            fields: List of field names to read (None for all fields)
            **kwargs: Additional parameters (limit, offset, order)

        Returns:
            List of dictionaries containing record data
        """
        if fields:
            kwargs["fields"] = fields
        return self.execute_kw(model, "search_read", [domain], kwargs)

    def fields_get(
        self, model: str, attributes: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Get field definitions for a model.

        Args:
            model: The Odoo model name
            attributes: List of field attributes to return

        Returns:
            Dictionary mapping field names to their definitions
        """
        # Check cache first
        cached_fields = self._performance_manager.get_cached_fields(model)
        if cached_fields and not attributes:  # Only use cache if no specific attributes requested
            logger.debug(f"Field definitions for {model} retrieved from cache")
            return cached_fields

        # Get fields from server
        kwargs = {}
        if attributes:
            kwargs["attributes"] = attributes

        with self._performance_manager.monitor.track_operation(f"fields_get_{model}"):
            fields = self.execute_kw(model, "fields_get", [], kwargs)

        # Cache if we got all attributes
        if not attributes:
            self._performance_manager.cache_fields(model, fields)

        return fields

    def search_count(self, model: str, domain: List[Union[str, List[Any]]]) -> int:
        """Count records matching a domain.

        Args:
            model: The Odoo model name
            domain: Odoo domain filter

        Returns:
            Number of records matching the domain
        """
        return self.execute_kw(model, "search_count", [domain], {})

    def create(self, model: str, values: Dict[str, Any]) -> int:
        """Create a new record.

        Args:
            model: The Odoo model name
            values: Dictionary of field values for the new record

        Returns:
            ID of the created record

        Raises:
            OdooConnectionError: If creation fails
        """
        try:
            with self._performance_manager.monitor.track_operation(f"create_{model}"):
                record_id = self.execute_kw(model, "create", [values], {})
                # Invalidate cache for this model
                self._performance_manager.invalidate_record_cache(model)
                logger.info(f"Created {model} record with ID {record_id}")
                return record_id
        except Exception as e:
            logger.error(f"Failed to create {model} record: {e}")
            raise

    def write(self, model: str, ids: List[int], values: Dict[str, Any]) -> bool:
        """Update existing records.

        Args:
            model: The Odoo model name
            ids: List of record IDs to update
            values: Dictionary of field values to update

        Returns:
            True if update was successful

        Raises:
            OdooConnectionError: If update fails
        """
        try:
            with self._performance_manager.monitor.track_operation(f"write_{model}"):
                result = self.execute_kw(model, "write", [ids, values], {})
                # Invalidate cache for updated records
                for record_id in ids:
                    self._performance_manager.invalidate_record_cache(model, record_id)
                logger.info(f"Updated {len(ids)} {model} record(s)")
                return result
        except Exception as e:
            logger.error(f"Failed to update {model} records: {e}")
            raise

    def unlink(self, model: str, ids: List[int]) -> bool:
        """Delete records.

        Args:
            model: The Odoo model name
            ids: List of record IDs to delete

        Returns:
            True if deletion was successful

        Raises:
            OdooConnectionError: If deletion fails
        """
        try:
            with self._performance_manager.monitor.track_operation(f"unlink_{model}"):
                result = self.execute_kw(model, "unlink", [ids], {})
                # Invalidate cache for deleted records
                for record_id in ids:
                    self._performance_manager.invalidate_record_cache(model, record_id)
                logger.info(f"Deleted {len(ids)} {model} record(s)")
                return result
        except Exception as e:
            logger.error(f"Failed to delete {model} records: {e}")
            raise

    def get_server_version(self) -> Optional[Dict[str, Any]]:
        """Get Odoo server version information.

        Returns:
            Dictionary with version information or None if not connected
        """
        if not self._connected:
            return None

        try:
            result = self.common_proxy.version()
            # Handle XML-RPC return value which could be various types
            if isinstance(result, dict):
                return result
            elif result is None:
                return None
            else:
                # Convert to dict if it's not already
                return {"version": str(result)}
        except Exception as e:
            logger.error(f"Failed to get server version: {e}")
            return None


@contextmanager
def create_connection(config: OdooConfig, timeout: int = OdooConnection.DEFAULT_TIMEOUT):
    """Create a connection context manager.

    Args:
        config: OdooConfig object
        timeout: Connection timeout in seconds

    Yields:
        Connected OdooConnection instance

    Example:
        with create_connection(config) as conn:
            # Use connection
            version = conn.common_proxy.version()
    """
    conn = OdooConnection(config, timeout)
    try:
        conn.connect()
        yield conn
    finally:
        conn.disconnect()
