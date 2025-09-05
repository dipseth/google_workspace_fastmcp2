#!/bin/bash
# Run client tests from tests/client folder with JWT authentication disabled

echo "🧪 Running client tests from tests/client folder with JWT authentication disabled..."
export ENABLE_JWT_AUTH=false
uv run pytest tests/client/ "$@"