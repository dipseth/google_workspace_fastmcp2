#!/usr/bin/env python3
"""Verify per-user credential encryption.

Validates that encrypted credential files can only be decrypted with the
correct per-user API key + server secret (split-key model).  Supports both
legacy single-recipient and multi-recipient CEK envelope formats.

Usage:
    python scripts/verify_credential_encryption.py <per-user-api-key> [credential-file]

Arguments:
    per-user-api-key   The key shown on the OAuth success page.
    credential-file    Path to .enc file (default: first .enc in credentials/).

Security checks performed:
    1. Server secret alone CANNOT decrypt
    2. MCP_API_KEY alone CANNOT decrypt (if set)
    3. Per-user key + server secret CAN decrypt
"""

import argparse
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

CREDENTIALS_DIR = Path(__file__).resolve().parent.parent / "credentials"
SERVER_SECRET_FILE = CREDENTIALS_DIR / ".auth_encryption_key"


def find_default_credential_file() -> Path:
    """Find the first .enc credential file in the credentials directory."""
    enc_files = sorted(CREDENTIALS_DIR.glob("*_credentials.enc"))
    if not enc_files:
        print("No credential files found in credentials/")
        sys.exit(1)
    return enc_files[0]


def derive_fernet_key(per_user_key: str, server_secret: bytes) -> bytes:
    """Derive a Fernet key from per-user key + server secret via HKDF."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=server_secret,
        info=b"per-user-credential-encryption-v1",
    )
    return base64.urlsafe_b64encode(hkdf.derive(per_user_key.encode()))


def key_id(per_user_key: str) -> str:
    """Compute the key ID (full SHA-256 hex digest)."""
    return hashlib.sha256(per_user_key.encode()).hexdigest()


def mask(value: str, prefix: int = 8, suffix: int = 4) -> str:
    """Mask a sensitive string, showing only prefix and suffix."""
    if len(value) <= prefix + suffix:
        return value[:prefix] + "..."
    return f"{value[:prefix]}...{value[-suffix:]}"


def main():
    parser = argparse.ArgumentParser(
        description="Verify per-user credential encryption (split-key model)."
    )
    parser.add_argument(
        "api_key",
        help="Per-user API key from the OAuth success page",
    )
    parser.add_argument(
        "credential_file",
        nargs="?",
        type=Path,
        default=None,
        help="Path to .enc credential file (default: first in credentials/)",
    )
    args = parser.parse_args()

    cred_path = args.credential_file or find_default_credential_file()
    per_user_key = args.api_key

    # --- Load envelope ---
    with open(cred_path) as f:
        envelope = json.load(f)

    is_multi = "recipients" in envelope
    print(f"File:       {cred_path}")
    print(f"Format:     v={envelope['v']}, enc={envelope['enc']}")
    if is_multi:
        print(f"Recipients: {len(envelope['recipients'])} key(s)")
    print(f"Data:       {len(envelope['data'])} chars")
    print()

    encrypted_creds = base64.urlsafe_b64decode(envelope["data"].encode())

    # --- Load server secret ---
    if not SERVER_SECRET_FILE.exists():
        print(f"Server secret not found: {SERVER_SECRET_FILE}")
        sys.exit(1)
    with open(SERVER_SECRET_FILE, "rb") as f:
        server_secret = f.read()

    passed = 0
    failed = 0

    # --- Check 1: Server secret alone should NOT decrypt ---
    try:
        Fernet(server_secret).decrypt(encrypted_creds)
        print("FAIL  Server secret alone decrypted the file")
        failed += 1
    except Exception:
        print("PASS  Server secret alone cannot decrypt")
        passed += 1

    # --- Check 2: MCP_API_KEY alone should NOT decrypt ---
    mcp_key = os.getenv("MCP_API_KEY", "")
    if mcp_key:
        try:
            hkdf = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b"mcp-google-workspace-v1",
                info=b"credential-encryption",
            )
            derived = base64.urlsafe_b64encode(hkdf.derive(mcp_key.encode()))
            Fernet(derived).decrypt(encrypted_creds)
            print("FAIL  MCP_API_KEY alone decrypted the file")
            failed += 1
        except Exception:
            print("PASS  MCP_API_KEY alone cannot decrypt")
            passed += 1
    else:
        print("SKIP  MCP_API_KEY not set")

    # --- Check 3: Per-user key + server secret should decrypt ---
    kid = key_id(per_user_key)
    fernet_key = derive_fernet_key(per_user_key, server_secret)
    print()
    print(f"Per-user key: {mask(per_user_key)}")
    print(f"Key ID:       {kid}")

    try:
        if is_multi:
            wrapped_cek_b64 = envelope["recipients"].get(kid)
            if not wrapped_cek_b64:
                print(
                    f"FAIL  Key ID not found in {len(envelope['recipients'])} recipient(s)"
                )
                failed += 1
                _print_summary(passed, failed)
                return
            print("PASS  Key ID found in recipients")
            passed += 1

            wrapped_cek = base64.urlsafe_b64decode(wrapped_cek_b64.encode())
            cek = Fernet(fernet_key).decrypt(wrapped_cek)
            print("PASS  CEK unwrapped successfully")
            passed += 1

            decrypted = Fernet(cek).decrypt(encrypted_creds)
        else:
            decrypted = Fernet(fernet_key).decrypt(encrypted_creds)

        creds = json.loads(decrypted.decode())
        print("PASS  Credentials decrypted with per-user key + server secret")
        passed += 1

        print()
        print("Credential summary:")
        print(f"  token:         {mask(creds['token'], 12, 6)}")
        print(f"  refresh_token: {mask(creds['refresh_token'], 12, 6)}")
        print(f"  client_id:     {mask(creds['client_id'], 20, 0)}")
        print(f"  scopes:        {len(creds.get('scopes', []))}")
        print(f"  encrypted_at:  {creds.get('encrypted_at', 'N/A')}")

    except Exception as e:
        print(f"FAIL  Decryption failed: {type(e).__name__}: {e}")
        failed += 1

    _print_summary(passed, failed)


def _print_summary(passed: int, failed: int):
    print()
    total = passed + failed
    if failed == 0:
        print(f"All {total} checks passed.")
    else:
        print(f"{failed}/{total} checks FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
