#!/usr/bin/env bash
# check_fda.sh — Verify Full Disk Access is granted for reading iMessage chat.db
# Source this script or run it directly. Exits 1 with setup instructions if FDA is missing.

set -euo pipefail

DB="${HOME}/Library/Messages/chat.db"

check_fda() {
    # Quick test: try to read one row from chat.db
    if sqlite3 "$DB" "SELECT 1 FROM message LIMIT 1;" >/dev/null 2>&1; then
        return 0
    fi

    # FDA not granted — detect which terminal app needs it
    local app_name="your terminal app"
    local app_path=""
    local instructions=""

    # Detection priority: TERM_PROGRAM > parent process > frontmost app
    local term_program="${TERM_PROGRAM:-}"
    local parent_comm
    parent_comm="$(ps -o comm= -p "$PPID" 2>/dev/null || echo "")"
    local frontmost
    frontmost="$(osascript -e 'tell application "System Events" to get name of first process whose frontmost is true' 2>/dev/null || echo "")"

    if [[ "$term_program" == "vscode" ]] || [[ "$parent_comm" == *"code"* ]] || [[ "${frontmost,,}" == *"code"* ]]; then
        app_name="Visual Studio Code"
        app_path="/Applications/Visual Studio Code.app"
    elif [[ "$parent_comm" == *"pycharm"* ]] || [[ "${frontmost,,}" == *"pycharm"* ]]; then
        app_name="PyCharm"
        app_path="/Applications/PyCharm CE.app (or /Applications/PyCharm.app)"
    elif [[ "$term_program" == "iTerm.app" ]] || [[ "${frontmost,,}" == *"iterm"* ]]; then
        app_name="iTerm2"
        app_path="/Applications/iTerm.app"
    elif [[ "$term_program" == "Apple_Terminal" ]] || [[ "${frontmost,,}" == *"terminal"* ]]; then
        app_name="Terminal"
        app_path="/System/Applications/Utilities/Terminal.app"
    elif [[ "$parent_comm" == *"cursor"* ]] || [[ "${frontmost,,}" == *"cursor"* ]]; then
        app_name="Cursor"
        app_path="/Applications/Cursor.app"
    elif [[ "$parent_comm" == *"warp"* ]] || [[ "${frontmost,,}" == *"warp"* ]]; then
        app_name="Warp"
        app_path="/Applications/Warp.app"
    fi

    echo "ERROR: Full Disk Access (FDA) is required to read iMessage chat.db" >&2
    echo "" >&2
    echo "Setup instructions for ${app_name}:" >&2
    echo "  1. Open System Settings > Privacy & Security > Full Disk Access" >&2
    echo "  2. Click the '+' button (or toggle the lock to make changes)" >&2
    if [ -n "$app_path" ]; then
        echo "  3. Add: ${app_path}" >&2
    else
        echo "  3. Add your terminal application" >&2
    fi
    echo "  4. Toggle it ON" >&2
    echo "  5. RESTART ${app_name} completely (quit and reopen)" >&2
    echo "" >&2
    echo "After restarting, run this command to verify:" >&2
    echo "  sqlite3 ~/Library/Messages/chat.db 'SELECT 1 FROM message LIMIT 1;'" >&2
    return 1
}

# If sourced, just define the function. If executed directly, run it.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    check_fda
fi