#!/usr/bin/env bash
# permission_gate.sh — Claude Code PermissionRequest hook
#
# Routes IDE permission prompts through iMessage when phone mode is active.
# When phone mode is off, exits 0 silently (falls through to normal IDE prompt).
#
# Stdin: JSON from Claude Code with tool_name, tool_input, session_id, cwd
# Stdout: JSON decision (allow/deny) when phone mode is active
# Exit codes:
#   0 — proceed (allow decision JSON on stdout, or empty = IDE fallthrough)
#   2 — deny (stderr feedback sent to Claude)
#
# Env vars (overridable for testing):
#   PHONE_MODE_FLAG — path to flag file (default: /tmp/imessage-notify-phone-mode)
#   FLAG_TTL_SECONDS — max age of flag before considered stale (default: 14400 = 4h)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FLAG="${PHONE_MODE_FLAG:-/tmp/imessage-notify-phone-mode}"
FLAG_TTL="${FLAG_TTL_SECONDS:-14400}"

# ─── Check phone mode flag ───

if [ ! -f "$FLAG" ]; then
  exit 0
fi

# Check for stale flag (older than FLAG_TTL seconds)
flag_mtime="$(stat -f %m "$FLAG" 2>/dev/null || echo 0)"
now="$(date +%s)"
flag_age=$(( now - flag_mtime ))

if [ "$flag_age" -gt "$FLAG_TTL" ]; then
  rm -f "$FLAG"
  exit 0
fi

# ─── Read and parse stdin JSON ───

input="$(cat)"
if [ -z "$input" ]; then
  exit 0
fi

# Parse JSON fields using python3 (already a dependency of the project)
parsed="$(python3 -c "
import json, sys
try:
    data = json.loads(sys.argv[1])
    tool = data.get('tool_name', '')
    ti = data.get('tool_input', {})
    print(tool)
    # Encode tool_input as JSON for the script to use
    print(json.dumps(ti))
except (json.JSONDecodeError, KeyError):
    print('')
    print('{}')
" "$input" 2>/dev/null)" || { exit 0; }

tool_name="$(echo "$parsed" | head -1)"
tool_input_json="$(echo "$parsed" | tail -1)"

if [ -z "$tool_name" ]; then
  exit 0
fi

# ─── Format message by tool type ───

format_message() {
  local tool="$1"
  local input_json="$2"
  local detail

  case "$tool" in
    Bash)
      detail="$(python3 -c "
import json, sys
ti = json.loads(sys.argv[1])
cmd = ti.get('command', '(unknown)')
# Truncate long commands
if len(cmd) > 200:
    cmd = cmd[:200] + '...'
print(f'Run command: {cmd}')
" "$input_json" 2>/dev/null)" || detail="Run command: (unknown)"
      ;;
    Write)
      detail="$(python3 -c "
import json, sys
ti = json.loads(sys.argv[1])
fp = ti.get('file_path', '(unknown)')
content = ti.get('content', '')
print(f'Write file: {fp} ({len(content)} chars)')
" "$input_json" 2>/dev/null)" || detail="Write file: (unknown)"
      ;;
    Edit)
      detail="$(python3 -c "
import json, sys
ti = json.loads(sys.argv[1])
fp = ti.get('file_path', '(unknown)')
print(f'Edit file: {fp}')
" "$input_json" 2>/dev/null)" || detail="Edit file: (unknown)"
      ;;
    Read)
      detail="$(python3 -c "
import json, sys
ti = json.loads(sys.argv[1])
fp = ti.get('file_path', '(unknown)')
print(f'Read file: {fp}')
" "$input_json" 2>/dev/null)" || detail="Read file: (unknown)"
      ;;
    *)
      detail="Use tool: ${tool}"
      ;;
  esac

  echo "[Permission] Claude wants to:
${detail}
Allow? Reply YES or NO."
}

message="$(format_message "$tool_name" "$tool_input_json")"

# ─── Send via notify.sh and wait for reply ───

reply="$("${SCRIPT_DIR}/notify.sh" "$message" 300 10 2>/tmp/imessage-gate-notify-err)" \
  && notify_exit=0 || notify_exit=$?

notify_stderr=""
if [ -f /tmp/imessage-gate-notify-err ]; then
  notify_stderr="$(cat /tmp/imessage-gate-notify-err)"
  rm -f /tmp/imessage-gate-notify-err
fi

# If notify.sh failed to send (not a timeout), fall through to IDE
if [ "$notify_exit" -ne 0 ]; then
  if echo "$notify_stderr" | grep -qi "ERROR"; then
    # Send failure — fall through to IDE prompt
    exit 0
  fi
  # Timeout — deny with feedback
  echo "No reply received within timeout. Permission denied." >&2
  exit 2
fi

# ─── Parse reply ───

reply_lower="$(echo "$reply" | tr '[:upper:]' '[:lower:]' | xargs)"

allow_json='{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}'
deny_json='{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"deny"}}}'

case "$reply_lower" in
  yes|y)
    echo "$allow_json"
    exit 0
    ;;
  no|n)
    echo "$deny_json"
    exit 0
    ;;
  *)
    echo "$deny_json"
    exit 0
    ;;
esac
