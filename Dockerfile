# FastMCP2 Google Workspace Platform - Production Dockerfile
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    PATH="/root/.local/bin:$PATH"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv (Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Create app directory
WORKDIR /app

# Copy dependency files first (for better caching)
COPY pyproject.toml uv.lock README.md ./

# Copy application code (needed before uv sync for hatchling build)
COPY . .

# Install Python dependencies using uv
RUN uv sync --frozen

# Create credentials directory
RUN mkdir -p /app/credentials && \
    chmod 755 /app/credentials

# Expose port (default 8002)
EXPOSE 8002

# Health check using lightweight readiness endpoint
# Following Kubernetes best practices for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8002/ready || exit 1

# Run the server using uv
CMD ["uv", "run", "python", "server.py"]