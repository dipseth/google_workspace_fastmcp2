#!/bin/bash
# Run tests with JWT authentication disabled

echo "🧪 Running tests with JWT authentication disabled..."
export ENABLE_JWT_AUTH=false
uv run pytest "$@"