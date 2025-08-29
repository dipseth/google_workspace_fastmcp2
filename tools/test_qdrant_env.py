#!/usr/bin/env python
"""Simple test to verify Qdrant environment variables."""

import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

print("=" * 60)
print("QDRANT ENVIRONMENT TEST")
print("=" * 60)

# Check environment variables
qdrant_url = os.getenv("QDRANT_URL")
qdrant_key = os.getenv("QDRANT_KEY")

print("\nEnvironment Variables:")
print(f"  QDRANT_URL: {qdrant_url if qdrant_url else 'NOT SET'}")
print(f"  QDRANT_KEY: {'***' if qdrant_key and qdrant_key != 'NONE' else qdrant_key if qdrant_key else 'NOT SET'}")

if not qdrant_url:
    print("\n⚠️  QDRANT_URL not found in environment.")
    print("Please add these lines to your .env file:")
    print("QDRANT_URL=http://localhost:6333")
    print("QDRANT_KEY=NONE")
else:
    print(f"\n✅ Qdrant configured to use: {qdrant_url}")