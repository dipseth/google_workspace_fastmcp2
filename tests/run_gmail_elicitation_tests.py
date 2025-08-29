#!/usr/bin/env python3
"""
Test runner script for Gmail elicitation system tests.

This script provides a convenient way to run the Gmail elicitation system test suite
with proper configuration and output formatting.
"""

import subprocess
import sys
import os
from pathlib import Path


def check_prerequisites():
    """Check if prerequisites are met for running tests."""
    print("🔍 Checking prerequisites...")

    # Check if we're in the right directory
    if not Path("tests/test_gmail_elicitation_system.py").exists():
        print("❌ Error: test_gmail_elicitation_system.py not found in tests/ directory")
        print("   Please run this script from the project root directory")
        return False

    # Check if MCP server might be running (basic check)
    import socket
    server_host = os.getenv("MCP_SERVER_HOST", "localhost")
    server_port = int(os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002")))

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex((server_host, server_port))
    sock.close()

    if result != 0:
        print(f"⚠️  Warning: MCP server not detected on {server_host}:{server_port}")
        print("   Make sure to start the MCP server before running tests:")
        print(f"   python -m fastmcp2_drive_upload.server --host {server_host} --port {server_port}")
        print()
        print("   Tests will still run but may show authentication errors (which is expected)")
    else:
        print(f"✅ MCP server detected on {server_host}:{server_port}")

    return True


def run_tests(test_filter=None, verbose=True, html_report=None):
    """Run the Gmail elicitation system tests."""
    print("\n" + "=" * 80)
    print("🚀 Running Gmail Elicitation System Tests")
    print("=" * 80)

    # Build pytest command
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/test_gmail_elicitation_system.py",
        "--asyncio-mode=auto",
        "--tb=short"
    ]

    if verbose:
        cmd.append("-v")

    if test_filter:
        cmd.extend(["-k", test_filter])

    if html_report:
        cmd.extend(["--html", html_report, "--self-contained-html"])

    print(f"📋 Command: {' '.join(cmd)}")
    print()

    try:
        # Run the tests
        result = subprocess.run(cmd, cwd=Path.cwd())

        # Print results summary
        print("\n" + "=" * 80)
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 80)

        if result.returncode == 0:
            print("✅ ALL TESTS PASSED!")
            print("\n🎉 The Gmail elicitation system has been successfully validated!")
        else:
            print("❌ SOME TESTS FAILED")
            print("\n🔧 Troubleshooting:")
            print("   • Check if MCP server is running")
            print("   • Verify authentication is properly configured")
            print("   • Review test output for specific error messages")

        print("\n📈 Test Coverage Areas:")
        print("   ✓ Allow list configuration and parsing")
        print("   ✓ Management tools (add/remove/view)")
        print("   ✓ Resource system access")
        print("   ✓ Elicitation flow simulation")
        print("   ✓ Integration scenarios")
        print("   ✓ Edge cases and error handling")
        print("   ✓ Documentation validation")
        print("   ✓ Performance and reliability")

        return result.returncode == 0

    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False


def show_help():
    """Show help information."""
    print("""
Gmail Elicitation System Test Runner

USAGE:
    python tests/run_gmail_elicitation_tests.py [OPTIONS]

OPTIONS:
    --filter FILTER       Run only tests matching FILTER
    --quiet               Run tests in quiet mode (less verbose)
    --html REPORT.html    Generate HTML test report
    --help               Show this help message

EXAMPLES:
    # Run all tests
    python tests/run_gmail_elicitation_tests.py

    # Run only elicitation flow tests
    python tests/run_gmail_elicitation_tests.py --filter elicitation

    # Run tests quietly
    python tests/run_gmail_elicitation_tests.py --quiet

    # Generate HTML report
    python tests/run_gmail_elicitation_tests.py --html gmail_tests_report.html

ENVIRONMENT VARIABLES:
    MCP_SERVER_HOST       MCP server host (default: localhost)
    MCP_SERVER_PORT       MCP server port (default: 8002)
    TEST_EMAIL_ADDRESS    Test email for authenticated testing

For more information, see: tests/README_GMAIL_ELICITATION_TESTS.md
""")


def main():
    """Main entry point."""
    # Parse command line arguments
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        show_help()
        return 0

    # Check prerequisites
    if not check_prerequisites():
        return 1

    # Parse arguments
    test_filter = None
    verbose = True
    html_report = None

    i = 0
    while i < len(args):
        if args[i] == "--filter" and i + 1 < len(args):
            test_filter = args[i + 1]
            i += 2
        elif args[i] == "--quiet":
            verbose = False
            i += 1
        elif args[i] == "--html" and i + 1 < len(args):
            html_report = args[i + 1]
            i += 2
        else:
            print(f"❌ Unknown argument: {args[i]}")
            show_help()
            return 1

    # Run tests
    success = run_tests(test_filter=test_filter, verbose=verbose, html_report=html_report)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())