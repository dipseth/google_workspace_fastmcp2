#!/usr/bin/env python3
"""Clean up stale session tool states.

This script cleans up the session_tool_states.json file which can grow
large from test runs creating many sessions.

Usage:
    # Preview what would be cleaned (dry run)
    python scripts/cleanup_session_states.py

    # Actually clean up (keep sessions from last hour)
    python scripts/cleanup_session_states.py --execute

    # Clean sessions older than 24 hours
    python scripts/cleanup_session_states.py --execute --hours 24

    # Clean ALL sessions (reset to empty)
    python scripts/cleanup_session_states.py --execute --all
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_session_file_path() -> Path:
    """Get the path to the session tool states file."""
    try:
        from config.settings import settings
        return settings.session_tool_state_path
    except Exception:
        # Fallback to default location
        return Path("credentials/session_tool_states.json")


def load_sessions(file_path: Path) -> dict:
    """Load sessions from file."""
    if not file_path.exists():
        return {}

    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading sessions: {e}")
        return {}


def save_sessions(file_path: Path, sessions: dict) -> bool:
    """Save sessions to file."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            json.dump(sessions, f, indent=2, default=str)
        return True
    except IOError as e:
        print(f"Error saving sessions: {e}")
        return False


def cleanup_sessions(
    max_age_hours: float = 1.0,
    execute: bool = False,
    clear_all: bool = False,
) -> dict:
    """Clean up old session states.

    Args:
        max_age_hours: Maximum age in hours for sessions to keep
        execute: If True, actually delete; if False, just preview
        clear_all: If True, clear ALL sessions regardless of age

    Returns:
        Summary of cleanup operation
    """
    file_path = get_session_file_path()
    sessions = load_sessions(file_path)

    if not sessions:
        return {
            "file_path": str(file_path),
            "total_sessions": 0,
            "sessions_to_remove": 0,
            "sessions_to_keep": 0,
            "executed": False,
            "message": "No sessions found",
        }

    total = len(sessions)
    cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

    # Categorize sessions
    to_keep = {}
    to_remove = {}

    for session_id, data in sessions.items():
        if clear_all:
            to_remove[session_id] = data
        else:
            last_accessed_str = data.get("last_accessed")
            if last_accessed_str:
                try:
                    last_accessed = datetime.fromisoformat(last_accessed_str)
                    if last_accessed < cutoff_time:
                        to_remove[session_id] = data
                    else:
                        to_keep[session_id] = data
                except (ValueError, TypeError):
                    # Invalid date format, mark for removal
                    to_remove[session_id] = data
            else:
                # No timestamp, mark for removal
                to_remove[session_id] = data

    result = {
        "file_path": str(file_path),
        "file_size_mb": file_path.stat().st_size / (1024 * 1024) if file_path.exists() else 0,
        "total_sessions": total,
        "sessions_to_remove": len(to_remove),
        "sessions_to_keep": len(to_keep),
        "cutoff_time": cutoff_time.isoformat() if not clear_all else "N/A (clear all)",
        "executed": execute,
    }

    if execute:
        if save_sessions(file_path, to_keep):
            result["new_file_size_mb"] = file_path.stat().st_size / (1024 * 1024) if to_keep else 0
            result["message"] = f"Removed {len(to_remove)} sessions, kept {len(to_keep)}"
        else:
            result["message"] = "Failed to save cleaned sessions"
    else:
        result["message"] = f"Would remove {len(to_remove)} sessions, keep {len(to_keep)} (dry run)"

    return result


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Clean up stale session tool states",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete sessions (default is dry run)",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=1.0,
        help="Keep sessions newer than this many hours (default: 1)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Clear ALL sessions regardless of age",
    )

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("SESSION TOOL STATES CLEANUP")
    print("=" * 60)

    result = cleanup_sessions(
        max_age_hours=args.hours,
        execute=args.execute,
        clear_all=args.all,
    )

    print(f"   File: {result['file_path']}")
    if result.get('file_size_mb'):
        print(f"   File size: {result['file_size_mb']:.2f} MB")
    print(f"   Total sessions: {result['total_sessions']}")
    print(f"   Sessions to remove: {result['sessions_to_remove']}")
    print(f"   Sessions to keep: {result['sessions_to_keep']}")
    if result.get('cutoff_time'):
        print(f"   Cutoff time: {result['cutoff_time']}")
    print(f"   Mode: {'EXECUTE' if result['executed'] else 'DRY RUN'}")
    print()
    print(f"   {result['message']}")

    if result.get('new_file_size_mb') is not None:
        print(f"   New file size: {result['new_file_size_mb']:.2f} MB")

    print("=" * 60 + "\n")

    if not args.execute and result['sessions_to_remove'] > 0:
        print("Run with --execute to actually remove sessions")


if __name__ == "__main__":
    main()
