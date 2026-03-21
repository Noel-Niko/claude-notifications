#!/usr/bin/env bash
# notify.sh — Send an iMessage and wait for a reply
# Usage: notify.sh "Your message here" [timeout_seconds] [poll_interval_seconds]
#    or: echo "message" | notify.sh - [timeout_seconds] [poll_interval_seconds]
#    or: notify.sh -f /path/to/message.txt [timeout_seconds] [poll_interval_seconds]
# Output (stdout): The reply text, or exits 1 on timeout
#
# Supports multi-repo routing: messages are tagged with repo name and request ID.
# Replies are matched by request ID first, then by timestamp for the most recent pending request.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Accept message from argument, stdin ("-"), or file ("-f <path>")
if [ "${1:-}" = "-f" ]; then
  filepath="${2:?Usage: notify.sh -f <filepath> [timeout] [poll_interval]}"
  message="$(cat "$filepath")"
  rm -f "$filepath"
  shift 2
elif [ "${1:-}" = "-" ]; then
  message="$(cat)"
  shift
else
  message="${1:?Usage: notify.sh \"message text\" [timeout] [poll_interval] OR notify.sh -f <filepath> [timeout] [poll_interval]}"
  shift
fi
timeout="${1:-300}"
poll_interval="${2:-10}"

# Send the message and capture metadata (errors will propagate due to pipefail)
if ! send_output="$("${SCRIPT_DIR}/send.sh" "$message" 2>&1)"; then
    echo "ERROR: Failed to send iMessage. Details above." >&2
    exit 1
fi

# Parse the sent epoch and request ID from send.sh output
sent_epoch="$(echo "$send_output" | grep -o 'SENT_EPOCH=[0-9]*' | cut -d= -f2)"
req_id="$(echo "$send_output" | grep -o 'REQ_ID=[a-f0-9]*' | cut -d= -f2)"

# Validate parsing succeeded
if [ -z "$sent_epoch" ] || [ -z "$req_id" ]; then
    echo "ERROR: Failed to parse send.sh output. Got: $send_output" >&2
    exit 1
fi

echo "Sent [REQ-${req_id}]. Waiting for reply..." >&2

# Poll for the reply, passing req_id for ID-based matching
"${SCRIPT_DIR}/read.sh" "$sent_epoch" "$timeout" "$poll_interval" "$req_id"