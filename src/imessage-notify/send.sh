#!/usr/bin/env bash
# send.sh — Send a tagged iMessage and output the request ID + timestamp
# Usage: send.sh "Your message here"
#    or: echo "message" | send.sh -
# Output (stdout): REQ_ID=<id> SENT_EPOCH=<epoch>
#
# Messages are tagged with the repo name and a unique request ID:
#   [repo-name|REQ-a1b2c3d4] Your message here

set -euo pipefail

RECIPIENT="CHANGE_ME"
CHAT_ID="any;-;${RECIPIENT}"
PENDING_DIR="/tmp/imessage-notify-pending"

# Accept message from argument or stdin (use "-" to read stdin)
if [ "${1:-}" = "-" ]; then
  message="$(cat)"
else
  message="${1:?Usage: send.sh \"message text\" OR echo \"message\" | send.sh -}"
fi

# Auto-detect repo name from git, fall back to current directory name
repo_name="$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")"

# Generate a short request ID (first 8 chars of a UUID)
req_id="$(uuidgen | tr '[:upper:]' '[:lower:]' | cut -c1-8)"

# Tag the message with repo and request ID
tagged_message="[${repo_name}|REQ-${req_id}] ${message}"

# Escape special characters for AppleScript (quotes, backslashes)
# Replace \ with \\, then " with \"
escaped_message="${tagged_message//\\/\\\\}"
escaped_message="${escaped_message//\"/\\\"}"

# Capture timestamp just before sending (epoch seconds)
sent_epoch="$(date +%s)"

# Register as a pending request
mkdir -p "$PENDING_DIR"
echo "${sent_epoch}" > "${PENDING_DIR}/REQ-${req_id}"

# Check if Messages app is running
if ! pgrep -x "Messages" >/dev/null; then
    echo "ERROR: Messages app is not running. Please open Messages.app and sign in to iMessage." >&2
    echo "HELP: Open /System/Applications/Messages.app" >&2
    rm -f "${PENDING_DIR}/REQ-${req_id}"
    exit 1
fi

# Send via AppleScript - capture errors
applescript_output=$(osascript -e "
tell application \"Messages\"
    set targetChat to chat id \"${CHAT_ID}\"
    send \"${escaped_message}\" to targetChat
end tell
" 2>&1)
applescript_exit=$?

if [ $applescript_exit -ne 0 ]; then
    echo "ERROR: Failed to send iMessage via AppleScript (exit code: $applescript_exit)" >&2
    echo "AppleScript error: $applescript_output" >&2
    echo "" >&2
    echo "TROUBLESHOOTING:" >&2
    echo "1. Verify Messages app is signed into iMessage (Messages > Settings > iMessage)" >&2
    echo "2. Check that you have an existing conversation with ${RECIPIENT}" >&2
    echo "3. Try sending a manual test message to ${RECIPIENT} in Messages app" >&2
    echo "4. Verify Full Disk Access: ~/.claude/skills/imessage-notify/check_fda.sh" >&2
    rm -f "${PENDING_DIR}/REQ-${req_id}"
    exit 1
fi

echo "REQ_ID=${req_id} SENT_EPOCH=${sent_epoch}"