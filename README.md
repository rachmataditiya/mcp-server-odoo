# MCP Server for Odoo

[![CI](https://github.com/ivnvxd/mcp-server-odoo/actions/workflows/ci.yml/badge.svg)](https://github.com/ivnvxd/mcp-server-odoo/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/ivnvxd/mcp-server-odoo/branch/main/graph/badge.svg)](https://codecov.io/gh/ivnvxd/mcp-server-odoo)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](https://opensource.org/licenses/MPL-2.0)

An MCP server that enables AI assistants like Claude to interact with Odoo ERP systems. Access business data, search records, create new entries, update existing data, and manage your Odoo instance through natural language.

## Features

- 🔍 **Search and retrieve** any Odoo record (customers, products, invoices, etc.)
- ✨ **Create new records** with field validation and permission checks
- ✏️ **Update existing data** with smart field handling
- 🗑️ **Delete records** respecting model-level permissions
- 📊 **Browse multiple records** and get formatted summaries
- 🔢 **Count records** matching specific criteria
- 📋 **Inspect model fields** to understand data structure
- 🔐 **Secure access** with API key or username/password authentication
- 🎯 **Smart pagination** for large datasets
- 💬 **LLM-optimized output** with hierarchical text formatting

## Odoo External API Compliance

This MCP server is fully compliant with the [Odoo External API documentation](https://odoo-documentation.oeerp.com/developer/api/external_api.html) and implements all standard XML-RPC endpoints and methods:

### Standard XML-RPC Endpoints

The server automatically detects and uses the appropriate endpoints in order of preference:

1. **MCP-specific endpoints** (if MCP addon is installed):
   - `/mcp/xmlrpc/db`
   - `/mcp/xmlrpc/common` 
   - `/mcp/xmlrpc/object`

2. **Standard Odoo endpoints** (fallback for vanilla installations):
   - `/xmlrpc/2/db`
   - `/xmlrpc/2/common`
   - `/xmlrpc/2/object`

3. **Alternative endpoints** (some Odoo installations):
   - `/xmlrpc/db`
   - `/xmlrpc/common`
   - `/xmlrpc/object`

4. **Legacy endpoints** (older Odoo versions):
   - `/xmlrpc/1/db`
   - `/xmlrpc/1/common`
   - `/xmlrpc/1/object`

### Authentication Methods

Following Odoo's standard authentication patterns:

- **API Key Authentication**: Modern approach using custom headers
- **Username/Password Authentication**: Traditional approach using `common.authenticate(db, username, password, user_agent_env)`

### Standard Odoo Methods

All standard Odoo XML-RPC methods are supported:

- **CRUD Operations**: `create()`, `read()`, `write()`, `unlink()`
- **Search Operations**: `search()`, `search_read()`, `search_count()`
- **Model Introspection**: `fields_get()`, model discovery via `ir.model`
- **Database Operations**: `list()`, `authenticate()`, `version()`

### Error Handling

Comprehensive error handling for common Odoo scenarios:

- Invalid credentials
- Database not found
- User not found
- Access denied
- Network timeouts
- 301 redirects (automatic HTTPS fallback)

## Installation

### Prerequisites

- Python 3.10 or higher
- Access to an Odoo instance (version 18.0)
- The [Odoo MCP module](https://apps.odoo.com/apps/modules/18.0/mcp_server) installed on your Odoo server
- An API key generated in Odoo (Settings > Users > API Keys)

### Install UV First

The MCP server runs on your **local computer** (where Claude Desktop is installed), not on your Odoo server. You need to install UV on your local machine:

<details>
<summary>macOS/Linux</summary>

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
</details>

<details>
<summary>Windows</summary>

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```
</details>

After installation, restart your terminal to ensure UV is in your PATH.

### Installing via MCP Settings (Recommended)

Add this configuration to your MCP settings:

<details>
<summary>Claude Desktop</summary>

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "uvx",
      "args": ["mcp-server-odoo"],
      "env": {
        "ODOO_URL": "https://your-odoo-instance.com",
        "ODOO_API_KEY": "your-api-key-here",
        "ODOO_DB": "your-database-name"
      }
    }
  }
}
```
</details>

<details>
<summary>Cursor</summary>

Add to `~/.cursor/mcp_settings.json`:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "uvx",
      "args": ["mcp-server-odoo"],
      "env": {
        "ODOO_URL": "https://your-odoo-instance.com",
        "ODOO_API_KEY": "your-api-key-here",
        "ODOO_DB": "your-database-name"
      }
    }
  }
}
```
</details>

<details>
<summary>VS Code (with GitHub Copilot)</summary>

Add to your VS Code settings (`~/.vscode/mcp_settings.json` or workspace settings):

```json
{
  "github.copilot.chat.mcpServers": {
    "odoo": {
      "command": "uvx",
      "args": ["mcp-server-odoo"],
      "env": {
        "ODOO_URL": "https://your-odoo-instance.com",
        "ODOO_API_KEY": "your-api-key-here",
        "ODOO_DB": "your-database-name"
      }
    }
  }
}
```
</details>

<details>
<summary>Zed</summary>

Add to `~/.config/zed/settings.json`:

```json
{
  "context_servers": {
    "odoo": {
      "command": "uvx",
      "args": ["mcp-server-odoo"],
      "env": {
        "ODOO_URL": "https://your-odoo-instance.com",
        "ODOO_API_KEY": "your-api-key-here",
        "ODOO_DB": "your-database-name"
      }
    }
  }
}
```
</details>

### Alternative Installation Methods

<details>
<summary>Using pip</summary>

```bash
# Install globally
pip install mcp-server-odoo

# Or use pipx for isolated environment
pipx install mcp-server-odoo
```

Then use `mcp-server-odoo` as the command in your MCP configuration.
</details>

<details>
<summary>From source</summary>

```bash
git clone https://github.com/ivnvxd/mcp-server-odoo.git
cd mcp-server-odoo
pip install -e .
```

Then use the full path to the package in your MCP configuration.
</details>

## Configuration

### Environment Variables

The server requires the following environment variables:

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `ODOO_URL` | Yes | Your Odoo instance URL | `https://mycompany.odoo.com` |
| `ODOO_API_KEY` | Yes* | API key for authentication | `0ef5b399e9ee9c11b053dfb6eeba8de473c29fcd` |
| `ODOO_USER` | Yes* | Username (if not using API key) | `admin` |
| `ODOO_PASSWORD` | Yes* | Password (if not using API key) | `admin` |
| `ODOO_DB` | No | Database name (auto-detected if not set) | `mycompany` |

*Either `ODOO_API_KEY` or both `ODOO_USER` and `ODOO_PASSWORD` are required.

**Notes:**
- If database listing is restricted on your server, you must specify `ODOO_DB`
- API key authentication is recommended for better security

### Transport Options

The server supports multiple transport protocols for different use cases:

#### 1. **stdio** (Default)
Standard input/output transport - used by desktop AI applications like Claude Desktop.

```bash
# Default transport - no additional configuration needed
uvx mcp-server-odoo
```

#### 2. **streamable-http**
Standard HTTP transport for REST API-style access and remote connectivity.

```bash
# Run with HTTP transport
uvx mcp-server-odoo --transport streamable-http --host 0.0.0.0 --port 8000

# Or use environment variables
export ODOO_MCP_TRANSPORT=streamable-http
export ODOO_MCP_HOST=0.0.0.0
export ODOO_MCP_PORT=8000
uvx mcp-server-odoo
```

The HTTP endpoint will be available at: `http://localhost:8000/mcp/`

> **Note**: SSE (Server-Sent Events) transport has been deprecated in MCP protocol version 2025-03-26. Use streamable-http transport instead for HTTP-based communication. Requires MCP library v1.9.4 or higher for proper session management.

#### Transport Configuration

| Variable/Flag | Description | Default |
|--------------|-------------|---------|
| `ODOO_MCP_TRANSPORT` / `--transport` | Transport type: stdio, streamable-http | `stdio` |
| `ODOO_MCP_HOST` / `--host` | Host to bind for HTTP transports | `localhost` |
| `ODOO_MCP_PORT` / `--port` | Port to bind for HTTP transports | `8000` |

**Example: Running streamable-http transport for remote access**

```json
{
  "mcpServers": {
    "odoo-remote": {
      "command": "uvx",
      "args": ["mcp-server-odoo", "--transport", "streamable-http", "--port", "8080"],
      "env": {
        "ODOO_URL": "https://your-odoo-instance.com",
        "ODOO_API_KEY": "your-api-key-here",
        "ODOO_DB": "your-database-name"
      }
    }
  }
}
```

### Setting up Odoo

1. **Install the MCP module**:
   - Download the [mcp_server module](https://github.com/ivnvxd/mcp-server-odoo/tree/main/odoo-apps/mcp_server)
   - Install it in your Odoo instance
   - Navigate to Settings > MCP Server

2. **Enable models for MCP access**:
   - Go to Settings > MCP Server > Enabled Models
   - Add models you want to access (e.g., res.partner, product.product)
   - Configure permissions (read, write, create, delete) per model

3. **Generate an API key**:
   - Go to Settings > Users & Companies > Users
   - Select your user
   - Under the "API Keys" tab, create a new key
   - Copy the key for your MCP configuration

## Usage Examples

Once configured, you can ask Claude:

**Search & Retrieve:**
- "Show me all customers from Spain"
- "Find products with stock below 10 units"
- "List today's sales orders over $1000"
- "Search for unpaid invoices from last month"
- "Count how many active employees we have"
- "Show me the contact information for Microsoft"

**Create & Manage:**
- "Create a new customer contact for Acme Corporation"
- "Add a new product called 'Premium Widget' with price $99.99"
- "Create a calendar event for tomorrow at 2 PM"
- "Update the phone number for customer John Doe to +1-555-0123"
- "Change the status of order SO/2024/001 to confirmed"
- "Delete the test contact we created earlier"

## Available Tools

### `search_records`
Search for records in any Odoo model with filters.

```json
{
  "model": "res.partner",
  "domain": [["is_company", "=", true], ["country_id.code", "=", "ES"]],
  "fields": ["name", "email", "phone"],
  "limit": 10
}
```

**Field Selection Options:**
- Omit `fields` or set to `null`: Returns smart selection of common fields
- Specify field list: Returns only those specific fields
- Use `["__all__"]`: Returns all fields (use with caution)

### `get_record`
Retrieve a specific record by ID.

```json
{
  "model": "res.partner",
  "record_id": 42,
  "fields": ["name", "email", "street", "city"]
}
```

**Field Selection Options:**
- Omit `fields` or set to `null`: Returns smart selection of common fields with metadata
- Specify field list: Returns only those specific fields
- Use `["__all__"]`: Returns all fields without metadata

### `list_models`
List all models enabled for MCP access.

```json
{}
```

### `create_record`
Create a new record in Odoo.

```json
{
  "model": "res.partner",
  "values": {
    "name": "New Customer",
    "email": "customer@example.com",
    "is_company": true
  }
}
```

### `update_record`
Update an existing record.

```json
{
  "model": "res.partner",
  "record_id": 42,
  "values": {
    "phone": "+1234567890",
    "website": "https://example.com"
  }
}
```

### `delete_record`
Delete a record from Odoo.

```json
{
  "model": "res.partner",
  "record_id": 42
}
```

## Resources

The server also provides direct access to Odoo data through resource URIs:

- `odoo://res.partner/record/1` - Get partner with ID 1
- `odoo://product.product/search?domain=[["qty_available",">",0]]` - Search products in stock
- `odoo://sale.order/browse?ids=1,2,3` - Browse multiple sales orders
- `odoo://res.partner/count?domain=[["customer_rank",">",0]]` - Count customers
- `odoo://product.product/fields` - List available fields for products

## Security

- Always use HTTPS in production environments
- Keep your API keys secure and rotate them regularly
- Configure model access carefully - only enable necessary models
- The MCP module respects Odoo's built-in access rights and record rules
- Each API key is linked to a specific user with their permissions

## Troubleshooting

<details>
<summary>Connection Issues</summary>

If you're getting connection errors:
1. Verify your Odoo URL is correct and accessible
2. Check that the MCP module is installed: visit `https://your-odoo.com/mcp/health`
3. Ensure your firewall allows connections to Odoo
</details>

<details>
<summary>Authentication Errors</summary>

If authentication fails:
1. Verify your API key is active in Odoo
2. Check that the user has appropriate permissions
3. Try regenerating the API key
4. For username/password auth, ensure 2FA is not enabled
</details>

<details>
<summary>Model Access Errors</summary>

If you can't access certain models:
1. Go to Settings > MCP Server > Enabled Models in Odoo
2. Ensure the model is in the list and has appropriate permissions
3. Check that your user has access to that model in Odoo's security settings
</details>

<details>
<summary>"spawn uvx ENOENT" Error</summary>

This error means UV is not installed or not in your PATH:

**Solution 1: Install UV** (see Installation section above)

**Solution 2: macOS PATH Issue**
Claude Desktop on macOS doesn't inherit your shell's PATH. Try:
1. Quit Claude Desktop completely (Cmd+Q)
2. Open Terminal
3. Launch Claude from Terminal:
   ```bash
   open -a "Claude"
   ```

**Solution 3: Use Full Path**
Find UV location and use full path:
```bash
which uvx
# Example output: /Users/yourname/.local/bin/uvx
```

Then update your config:
```json
{
  "command": "/Users/yourname/.local/bin/uvx",
  "args": ["mcp-server-odoo"]
}
```
</details>

<details>
<summary>Database Configuration Issues</summary>

If you see "Access Denied" when listing databases:
- This is normal - some Odoo instances restrict database listing for security
- Make sure to specify `ODOO_DB` in your configuration
- The server will use your specified database without validation

Example configuration:
```json
{
  "env": {
    "ODOO_URL": "https://your-odoo.com",
    "ODOO_API_KEY": "your-key",
    "ODOO_DB": "your-database-name"
  }
}
```
Note: `ODOO_DB` is required if database listing is restricted on your server.
</details>

<details>
<summary>Debug Mode</summary>

Enable debug logging for more information:

```json
{
  "env": {
    "ODOO_URL": "https://your-odoo.com",
    "ODOO_API_KEY": "your-key",
    "ODOO_MCP_LOG_LEVEL": "DEBUG"
  }
}
```
</details>

## Development

<details>
<summary>Running from source</summary>

```bash
# Clone the repository
git clone https://github.com/ivnvxd/mcp-server-odoo.git
cd mcp-server-odoo

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest --cov

# Run the server
python -m mcp_server_odoo
```
</details>

<details>
<summary>Testing with MCP Inspector</summary>

```bash
# Using uvx
npx @modelcontextprotocol/inspector uvx mcp-server-odoo

# Using local installation
npx @modelcontextprotocol/inspector python -m mcp_server_odoo
```
</details>

## Testing

### Transport Tests

You can test both stdio and streamable-http transports to ensure they're working correctly:

```bash
# Run comprehensive transport tests
python tests/run_transport_tests.py
```

This will test:
- **stdio transport**: Basic initialization and communication
- **streamable-http transport**: HTTP endpoint, session management, and tool calls

### Unit Tests

For complete testing including unit and integration tests:

```bash
# Run all tests
uv run pytest --cov

# Run specific test categories
uv run pytest tests/test_tools.py -v
uv run pytest tests/test_server_foundation.py -v
```

## License

This project is licensed under the Mozilla Public License 2.0 (MPL-2.0) - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are very welcome! Please see the [CONTRIBUTING](CONTRIBUTING.md) guide for details.

## Support

Thank you for using this project! If you find it helpful and would like to support my work, kindly consider buying me a coffee. Your support is greatly appreciated!

<a href="https://www.buymeacoffee.com/ivnvxd" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>

And do not forget to give the project a star if you like it! :star: