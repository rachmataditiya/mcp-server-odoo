# MCP Server for Odoo - No Addon Required

## Overview

The MCP server has been **completely modified** to work with **vanilla Odoo installations without requiring any addons**. It now supports:

1. **Vanilla Odoo** (primary) - Uses standard `/xmlrpc/2/*` endpoints
2. **Odoo with MCP addon** (optional) - Uses `/mcp/xmlrpc/*` endpoints for enhanced features

## How It Works

### Automatic Endpoint Detection
The server automatically detects which endpoints are available:

1. **First, tries MCP endpoints:**
   - `/mcp/xmlrpc/db`
   - `/mcp/xmlrpc/common` 
   - `/mcp/xmlrpc/object`

2. **If MCP endpoints fail, falls back to standard Odoo endpoints:**
   - `/xmlrpc/2/db`
   - `/xmlrpc/2/common`
   - `/xmlrpc/2/object`

### Access Control
The access control system has been completely rewritten to work without addons:

- **With MCP addon**: Uses `mcp.enabled.model` for granular permissions
- **Without addon**: Uses standard Odoo access rights and model discovery
- **Automatic detection**: Chooses the appropriate method based on availability

### Benefits

✅ **Zero addon requirements** - Works with any Odoo installation  
✅ **Backward compatible** - Still supports MCP addon if available  
✅ **Automatic detection** - No configuration needed  
✅ **Same functionality** - All MCP features work with standard endpoints  
✅ **Enhanced security** - Uses Odoo's built-in access control system  

## Usage

### With Vanilla Odoo (No Addon Required)

```yaml
# docker-compose.yml
services:
  mcp-server:
    build: .
    environment:
      - ODOO_URL=https://your-odoo-instance.com
      - ODOO_DB=your_database_name
      - ODOO_API_KEY=your_api_key_here
      # or use username/password:
      # - ODOO_USER=your_username
      # - ODOO_PASSWORD=your_password
```

### With Odoo + MCP Addon (Enhanced Features)

If you have the MCP addon installed, the server will automatically use the MCP-specific endpoints and enhanced access control for better performance and additional features.

## Authentication

Both endpoint types support the same authentication methods:

### API Key (Recommended)
```yaml
- ODOO_API_KEY=your_api_key_here
```

### Username/Password
```yaml
- ODOO_USER=your_username
- ODOO_PASSWORD=your_password
```

## Logging

The server logs which endpoint type and access control method it's using:

```
INFO: Using standard Odoo XML-RPC endpoints
INFO: MCP addon not available - using basic access control
```
or
```
INFO: Using MCP-specific endpoints
INFO: MCP addon detected - using enhanced access control
```

## Technical Details

### What Changed

1. **Endpoint Fallback**: Added automatic fallback from MCP to standard endpoints
2. **Access Control Rewrite**: Completely rewrote access control to work without addons
3. **Model Discovery**: Uses standard `ir.model` for model discovery
4. **Permission Checking**: Uses Odoo's built-in access rights system
5. **Error Handling**: Enhanced error handling for both scenarios

### Access Control Methods

#### With MCP Addon
- Uses `mcp.enabled.model` for granular permissions
- Supports per-model read/write/create/delete permissions
- Enhanced caching and performance

#### Without Addon
- Uses standard Odoo access rights
- Discovers accessible models via `ir.model`
- Assumes full permissions for accessible models
- Falls back gracefully on errors

## Troubleshooting

### Connection Issues
- Ensure Odoo XML-RPC is enabled (it is by default)
- Check firewall settings for port 8069 (or your custom port)
- Verify credentials are correct

### Access Control Issues
- **With addon**: Check MCP module configuration in Odoo
- **Without addon**: Check user permissions in Odoo settings
- Both methods respect Odoo's built-in access rights

### Performance
- MCP endpoints provide better performance if available
- Standard endpoints work but may be slightly slower
- Both support connection pooling for optimization

## Migration

If you're upgrading from a version that required the MCP addon:

1. **No changes needed** - The server will automatically detect available endpoints
2. **Optional** - You can still install the MCP addon for enhanced features
3. **Backward compatible** - Existing configurations continue to work

## Security Notes

- Both endpoint types use the same security model
- API key authentication is recommended over username/password
- All connections use HTTPS when available
- Error messages are sanitized to prevent information leakage
- Access control respects Odoo's built-in security system 