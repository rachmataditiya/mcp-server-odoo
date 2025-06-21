# Gunakan Python 3.11 image yang ringan
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency files terlebih dahulu (untuk cache optimal)
COPY pyproject.toml uv.lock* README.md ./

# Salin source code ke dalam container
COPY mcp_server_odoo ./mcp_server_odoo

# Pastikan folder mcp_server_odoo punya __init__.py
RUN touch mcp_server_odoo/__init__.py

# Install dependencies & project
RUN uv pip install . --system

# Expose port
EXPOSE 8000

# Jalankan server
CMD ["mcp-server-odoo", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]