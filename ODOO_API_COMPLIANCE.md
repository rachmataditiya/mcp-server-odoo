# Odoo External API Compliance

This document details how the MCP Server for Odoo implements and complies with the [Odoo External API documentation](https://odoo-documentation.oeerp.com/developer/api/external_api.html).

## Overview

The MCP Server for Odoo is designed to work seamlessly with both vanilla Odoo installations and those with MCP-specific addons. It implements all standard Odoo XML-RPC endpoints and methods while providing additional MCP-specific functionality when available.

## XML-RPC Endpoints

### Endpoint Detection Strategy

The server automatically detects available endpoints in order of preference:

```python
# MCP-specific endpoints (preferred)
MCP_DB_ENDPOINT = "/mcp/xmlrpc/db"
MCP_COMMON_ENDPOINT = "/mcp/xmlrpc/common"
MCP_OBJECT_ENDPOINT = "/mcp/xmlrpc/object"

# Standard Odoo endpoints (fallback)
STANDARD_DB_ENDPOINT = "/xmlrpc/2/db"
STANDARD_COMMON_ENDPOINT = "/xmlrpc/2/common"
STANDARD_OBJECT_ENDPOINT = "/xmlrpc/2/object"

# Alternative endpoints
ALT_DB_ENDPOINT = "/xmlrpc/db"
ALT_COMMON_ENDPOINT = "/xmlrpc/common"
ALT_OBJECT_ENDPOINT = "/xmlrpc/object"

# Legacy endpoints
LEGACY_DB_ENDPOINT = "/xmlrpc/1/db"
LEGACY_COMMON_ENDPOINT = "/xmlrpc/1/common"
LEGACY_OBJECT_ENDPOINT = "/xmlrpc/1/object"
```

### Automatic Fallback

If MCP endpoints are not available, the server automatically falls back to standard Odoo endpoints:

1. **Test MCP endpoints** first
2. **Test standard endpoints** (`/xmlrpc/2/*`)
3. **Test alternative endpoints** (`/xmlrpc/*`)
4. **Test legacy endpoints** (`/xmlrpc/1/*`)
5. **Try HTTPS** if HTTP fails (handles 301 redirects)

## Authentication Methods

### 1. API Key Authentication (Modern)

```python
def _authenticate_api_key(self, database: str) -> bool:
    """Authenticate using API key via custom endpoint."""
    url = f"{base_url}/mcp/auth/validate"
    req = urllib.request.Request(url)
    req.add_header("X-API-Key", self.config.api_key)
    # ... validation logic
```

### 2. Username/Password Authentication (Standard)

```python
def _authenticate_password(self, database: str) -> bool:
    """Authenticate using standard Odoo method."""
    uid = self.common_proxy.authenticate(
        database, self.config.username, self.config.password, {}
    )
    # ... validation logic
```

**Compliance**: Uses the exact signature from Odoo documentation: `authenticate(db, username, password, user_agent_env)`

## Standard Odoo Methods Implementation

### Database Operations

#### List Databases
```python
def list_databases(self) -> List[str]:
    """List all available databases."""
    return self.db_proxy.list()
```

**Compliance**: Uses standard `db.list()` method as documented.

#### Server Version
```python
def get_server_version(self) -> Optional[Dict[str, Any]]:
    """Get Odoo server version information."""
    return self.common_proxy.version()
```

**Compliance**: Uses standard `common.version()` method.

### CRUD Operations

#### Create Records
```python
def create(self, model: str, values: Dict[str, Any]) -> int:
    """Create a new record."""
    return self.execute_kw(model, "create", [values], {})
```

**Compliance**: Uses standard `execute_kw(model, 'create', [values], {})` pattern.

#### Read Records
```python
def read(self, model: str, ids: List[int], fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Read record data."""
    kwargs = {"fields": fields} if fields else {}
    return self.execute_kw(model, "read", [ids], kwargs)
```

**Compliance**: Uses standard `execute_kw(model, 'read', [ids], kwargs)` pattern.

#### Update Records
```python
def write(self, model: str, ids: List[int], values: Dict[str, Any]) -> bool:
    """Update existing records."""
    return self.execute_kw(model, "write", [ids, values], {})
```

**Compliance**: Uses standard `execute_kw(model, 'write', [ids, values], {})` pattern.

#### Delete Records
```python
def unlink(self, model: str, ids: List[int]) -> bool:
    """Delete records."""
    return self.execute_kw(model, "unlink", [ids], {})
```

**Compliance**: Uses standard `execute_kw(model, 'unlink', [ids], {})` pattern.

### Search Operations

#### Search Records
```python
def search(self, model: str, domain: List[Union[str, List[Any]]], **kwargs) -> List[int]:
    """Search for records matching domain."""
    return self.execute_kw(model, "search", [domain], kwargs)
```

**Compliance**: Uses standard `execute_kw(model, 'search', [domain], kwargs)` pattern.

#### Search and Read
```python
def search_read(self, model: str, domain: List[Union[str, List[Any]]], 
                fields: Optional[List[str]] = None, **kwargs) -> List[Dict[str, Any]]:
    """Search for records and read their data in one operation."""
    if fields:
        kwargs["fields"] = fields
    return self.execute_kw(model, "search_read", [domain], kwargs)
```

**Compliance**: Uses standard `execute_kw(model, 'search_read', [domain], kwargs)` pattern.

#### Count Records
```python
def search_count(self, model: str, domain: List[Union[str, List[Any]]]) -> int:
    """Count records matching a domain."""
    return self.execute_kw(model, "search_count", [domain], {})
```

**Compliance**: Uses standard `execute_kw(model, 'search_count', [domain], {})` pattern.

### Model Introspection

#### Get Field Definitions
```python
def fields_get(self, model: str, attributes: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """Get field definitions for a model."""
    kwargs = {"attributes": attributes} if attributes else {}
    return self.execute_kw(model, "fields_get", [], kwargs)
```

**Compliance**: Uses standard `execute_kw(model, 'fields_get', [], kwargs)` pattern.

#### Model Discovery
```python
def list_models(self) -> List[Dict[str, Any]]:
    """List all available models."""
    return self.search_read('ir.model', [('state', '=', 'base')], 
                           ['name', 'model', 'state'])
```

**Compliance**: Uses standard `ir.model` introspection as documented.

## Error Handling

### Standard Odoo Error Patterns

The server handles all standard Odoo XML-RPC errors:

```python
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
```

### Network Error Handling

```python
except socket.timeout:
    raise OdooConnectionError(f"Connection timeout after {self.timeout} seconds")
except socket.error as e:
    raise OdooConnectionError(f"Failed to connect to {host}:{port}: {e}")
```

### Redirect Handling

Automatic handling of 301 redirects:

```python
# If HTTP failed, try HTTPS
if self._url_components['scheme'] == 'http':
    logger.info("HTTP failed, trying HTTPS...")
    # Temporarily switch to HTTPS and retry
```

## Performance Optimizations

### Connection Pooling

```python
def get_optimized_connection(self, endpoint: str) -> xmlrpc.client.ServerProxy:
    """Get optimized XML-RPC connection with pooling."""
    # Implementation includes connection reuse and timeout optimization
```

### Caching

```python
def cache_record(self, model: str, record: Dict[str, Any], fields: Optional[List[str]] = None):
    """Cache frequently accessed records."""
    # Implementation includes TTL and memory management
```

## Testing Compliance

### Test Coverage

The test suite includes comprehensive coverage of all standard Odoo methods:

- `test_basic_resources.py`: Tests CRUD operations
- `test_search_resources.py`: Tests search operations  
- `test_write_operations.py`: Tests write operations
- `test_xmlrpc_operations.py`: Tests direct XML-RPC calls

### Example Test

```python
def test_standard_odoo_authentication():
    """Test standard Odoo authentication method."""
    conn = OdooConnection(config)
    conn.connect()
    
    # Test standard authenticate method
    uid = conn.common_proxy.authenticate(
        database, username, password, {}
    )
    assert isinstance(uid, int)
```

## Compatibility Matrix

| Odoo Version | MCP Endpoints | Standard Endpoints | Legacy Endpoints |
|--------------|---------------|-------------------|------------------|
| 16.0+        | ✅            | ✅                | ✅               |
| 15.0         | ✅            | ✅                | ✅               |
| 14.0         | ✅            | ✅                | ✅               |
| 13.0         | ✅            | ✅                | ✅               |
| 12.0         | ❌            | ✅                | ✅               |

## Conclusion

The MCP Server for Odoo maintains full compliance with the Odoo External API while providing additional MCP-specific functionality when available. This ensures:

1. **Backward Compatibility**: Works with older Odoo versions
2. **Forward Compatibility**: Supports newer Odoo features
3. **Standards Compliance**: Follows Odoo documentation exactly
4. **Flexibility**: Works with or without MCP addons
5. **Reliability**: Comprehensive error handling and fallback mechanisms

For more information about the Odoo External API, see the [official documentation](https://odoo-documentation.oeerp.com/developer/api/external_api.html). 