#!/usr/bin/env bash
# hook_notify.sh — Claude Code hook wrapper for iMessage notifications
# Called automatically by Claude Code hooks when user attention is needed.
# Reads hook JSON from stdin, debounces, and fires send.sh.
#
# This script is fire-and-forget — it does NOT wait for a reply.
# The user responds in the terminal as usual.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEBOUNCE_FILE="/tmp/imessage-notify-last-hook"
DEBOUNCE_SECONDS=30

# Debounce: skip if we notified within the last N seconds
if [ -f "$DEBOUNCE_FILE" ]; then
    last_sent="$(cat "$DEBOUNCE_FILE" 2>/dev/null || echo 0)"
    now="$(date +%s)"
    if [ $((now - last_sent)) -lt "$DEBOUNCE_SECONDS" ]; then
        exit 0
    fi
fi

# Read hook input from stdin
input="$(cat)"

# Extract context from the hook JSON
hook_event="$(echo "$input" | jq -r '.hook_event_name // "unknown"' 2>/dev/null || echo "unknown")"
matcher="$(echo "$input" | jq -r '.matcher // ""' 2>/dev/null || echo "")"
cwd="$(echo "$input" | jq -r '.cwd // ""' 2>/dev/null || echo "")"
repo_name="$(basename "${cwd:-unknown}" 2>/dev/null || echo "unknown")"

# Build message based on the notification type
case "$matcher" in
    idle_prompt)
        message="[${repo_name}] Claude is waiting for your input"
        ;;
    permission_prompt)
        message="[${repo_name}] Claude needs permission to proceed"
        ;;
    *)
        message="[${repo_name}] Claude needs your attention"
        ;;
esac

# Send the notification (fire-and-forget)
"${SCRIPT_DIR}/send.sh" "$message" >/dev/null 2>&1 || true

# Update debounce timestamp
date +%s > "$DEBOUNCE_FILE"

exit 0