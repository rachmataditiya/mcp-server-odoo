# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install uv, a fast Python package installer
RUN pip install uv

# Copy the dependency definitions
COPY pyproject.toml uv.lock* ./

# Install project dependencies using uv
RUN uv pip install .

# Copy the application code
COPY mcp_server_odoo/ ./mcp_server_odoo/

# Expose the port the app runs on
EXPOSE 8000

# Define the command to run the application
# We use the script defined in pyproject.toml
# The host is set to 0.0.0.0 to be accessible from outside the container
CMD ["mcp-server-odoo", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"] 