#!/usr/bin/env bash
# check_imessage.sh — Verify Messages.app is installed and iMessage is activated
#
# Checks:
#   1. Messages.app exists at /System/Applications/Messages.app
#   2. iMessage service is configured (via AppleScript query)
#
# Exit codes:
#   0 — Messages.app found and iMessage is active
#   1 — Messages.app not found
#   2 — Messages.app found but iMessage not activated or status unknown
#
# Source this script or run it directly.

set -euo pipefail

check_imessage() {
    # --- Check 1: Messages.app exists ---
    if [[ ! -d "/System/Applications/Messages.app" ]]; then
        echo "ERROR: Messages.app not found." >&2
        echo "" >&2
        echo "Messages.app ships with macOS and cannot be installed separately." >&2
        echo "" >&2
        echo "Checked: /System/Applications/Messages.app" >&2
        echo "" >&2
        echo "Troubleshooting:" >&2
        echo "  1. Search Spotlight (Cmd+Space) for 'Messages'" >&2
        echo "  2. If truly missing, reinstall macOS (without erasing data):" >&2
        echo "     Restart Mac > hold Cmd+R > Reinstall macOS" >&2
        return 1
    fi

    # --- Check 2: Ensure Messages.app is running ---
    if ! pgrep -x "Messages" >/dev/null; then
        echo "Starting Messages.app..." >&2
        open -a Messages
        sleep 2
    fi

    # --- Check 3: Query iMessage service via AppleScript ---
    local service_count
    service_count="$(osascript -e 'tell application "Messages" to count of (services whose service type is iMessage)' 2>/dev/null || echo "QUERY_FAILED")"

    if [[ "$service_count" == "QUERY_FAILED" ]]; then
        _print_query_failed_warning
        return 2
    fi

    if [[ "$service_count" -gt 0 ]]; then
        return 0
    fi

    # 0 iMessage services — not activated
    _print_activation_instructions
    return 2
}

_print_activation_instructions() {
    echo "WARNING: iMessage does not appear to be activated." >&2
    echo "" >&2
    echo "To activate iMessage:" >&2
    echo "  1. Open Messages.app" >&2
    echo "  2. Go to Messages > Settings > iMessage" >&2
    echo "  3. Sign in with your Apple ID" >&2
    echo "  4. Ensure your phone number or email appears under" >&2
    echo "     'You can be reached for messages at'" >&2
    echo "" >&2
    echo "If already signed in but iMessage is disabled:" >&2
    echo "  - Toggle 'Enable this account' OFF then ON again" >&2
    echo "  - Check Apple System Status: https://www.apple.com/support/systemstatus/" >&2
}

_print_query_failed_warning() {
    echo "WARNING: Could not confirm iMessage is activated." >&2
    echo "" >&2
    echo "This may be because:" >&2
    echo "  - Automation permission was denied for this terminal" >&2
    echo "  - Messages.app failed to respond" >&2
    echo "" >&2
    echo "To verify iMessage is set up:" >&2
    echo "  1. Open Messages.app" >&2
    echo "  2. Go to Messages > Settings > iMessage" >&2
    echo "  3. Confirm you are signed in with your Apple ID" >&2
}

# If sourced, just define the functions. If executed directly, run it.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    check_imessage
fi
