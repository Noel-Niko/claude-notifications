#!/usr/bin/env bash
# whitelist_commands.sh — Set up iMessage notifications for Claude Code
#
# What it does:
#   1. (Optional) Configures the RECIPIENT phone number or email in send.sh and read.sh
#   2. Adds wildcard permission entries to the current repo's .claude/settings.local.json
#   3. Adds wildcard permission entries to the global ~/.claude/settings.json
#   4. Injects PermissionRequest/SessionEnd/SessionStart hooks into global settings
#   5. Ensures all skill scripts are executable
#
# Usage:
#   cd /path/to/your/repo
#
#   # First-time setup (configure phone number + whitelist permissions):
#   ~/.claude/skills/imessage-notify/whitelist_commands.sh +13522339160
#   ~/.claude/skills/imessage-notify/whitelist_commands.sh 1-352-233-9160
#   ~/.claude/skills/imessage-notify/whitelist_commands.sh "(352) 233-9160"
#   ~/.claude/skills/imessage-notify/whitelist_commands.sh your.email@example.com
#
#   # Subsequent repos (permissions only, phone already configured):
#   ~/.claude/skills/imessage-notify/whitelist_commands.sh

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"

# Permission patterns to inject (tilde form + absolute form for sub-agent compat)
TILDE_SKILL="~/.claude/skills/imessage-notify"
ABS_SKILL="${HOME}/.claude/skills/imessage-notify"

PERMISSIONS=(
  "Bash(*)"
  "Bash(${TILDE_SKILL}/notify.sh *)"
  "Bash(${TILDE_SKILL}/send.sh *)"
  "Bash(${TILDE_SKILL}/read.sh *)"
  "Bash(${TILDE_SKILL}/check_fda.sh)"
  "Bash(${TILDE_SKILL}/check_imessage.sh)"
  "Bash(cat ${TILDE_SKILL}/*)"
  "Read(${TILDE_SKILL}/*)"
  "Bash(${ABS_SKILL}/notify.sh *)"
  "Bash(${ABS_SKILL}/send.sh *)"
  "Bash(${ABS_SKILL}/read.sh *)"
  "Bash(${ABS_SKILL}/check_fda.sh)"
  "Bash(${ABS_SKILL}/check_imessage.sh)"
  "Bash(cat ${ABS_SKILL}/*)"
  "Read(${ABS_SKILL}/*)"
)

# --- Helper: normalize phone number to +1XXXXXXXXXX ---
normalize_phone() {
  local input="$1"
  # Strip everything except digits and +
  local digits
  digits="$(echo "$input" | tr -cd '0-9+')"

  # Remove leading + if present, we'll add it back
  digits="${digits#+}"

  # If it starts with 1 and has 11 digits, it already has country code
  if [[ ${#digits} -eq 11 && "$digits" == 1* ]]; then
    echo "+${digits}"
  # If it has 10 digits, prepend +1
  elif [[ ${#digits} -eq 10 ]]; then
    echo "+1${digits}"
  else
    echo ""
  fi
}

# --- Helper: configure RECIPIENT in send.sh and read.sh ---
configure_recipient() {
  local recipient="$1"

  local send_file="${SKILL_DIR}/send.sh"
  local read_file="${SKILL_DIR}/read.sh"

  # Read current RECIPIENT from send.sh
  local current
  current="$(grep '^RECIPIENT=' "$send_file" | head -1 | sed 's/RECIPIENT="//' | sed 's/"$//')"

  if [ "$current" = "$recipient" ]; then
    echo "  RECIPIENT already set to: ${recipient}"
    return
  fi

  # Escape for sed (handle + and . in phone/email)
  local escaped
  escaped="$(echo "$recipient" | sed 's/[&/\]/\\&/g')"

  sed -i '' "s|^RECIPIENT=\".*\"|RECIPIENT=\"${escaped}\"|" "$send_file"
  sed -i '' "s|^RECIPIENT=\".*\"|RECIPIENT=\"${escaped}\"|" "$read_file"

  echo "  RECIPIENT updated to: ${recipient}"
  echo "  Updated: send.sh, read.sh"
}

# --- Helper: configure RECIPIENT_ALIASES in read.sh ---
configure_aliases() {
  local aliases="$1"
  local read_file="${SKILL_DIR}/read.sh"

  # Escape for sed (handle + and . in phone/email addresses)
  local escaped
  escaped="$(echo "$aliases" | sed 's/[&/\]/\\&/g')"

  sed -i '' "s|^RECIPIENT_ALIASES=\".*\"|RECIPIENT_ALIASES=\"${escaped}\"|" "$read_file"

  if [ -n "$aliases" ]; then
    echo "  RECIPIENT_ALIASES updated to: ${aliases}"
    echo "  Updated: read.sh"
  fi
}

# --- Helper: inject permissions into a settings JSON file ---
inject_permissions() {
  local settings_file="$1"

  python3 -c "
import json, os, sys

settings_file = sys.argv[1]
permissions = sys.argv[2:]

# Read existing settings or start fresh
if os.path.exists(settings_file):
    with open(settings_file, 'r') as f:
        settings = json.load(f)
else:
    os.makedirs(os.path.dirname(settings_file), exist_ok=True)
    settings = {}

# Ensure permissions.allow exists
if 'permissions' not in settings:
    settings['permissions'] = {}
if 'allow' not in settings['permissions']:
    settings['permissions']['allow'] = []

existing = set(settings['permissions']['allow'])
added = []
for perm in permissions:
    if perm not in existing:
        settings['permissions']['allow'].insert(0, perm)
        added.append(perm)

if added:
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)
        f.write('\n')
    for a in added:
        print(f'  + {a}')
else:
    print('  (all entries already present)')
" "$settings_file" "${PERMISSIONS[@]}"
}

# --- Helper: inject hooks into a settings JSON file ---
inject_hooks() {
  local settings_file="$1"
  local gate_cmd="$2"

  python3 -c "
import json, os, sys

settings_file = sys.argv[1]
gate_cmd = sys.argv[2]

# Read existing settings or start fresh
if os.path.exists(settings_file):
    with open(settings_file, 'r') as f:
        settings = json.load(f)
else:
    os.makedirs(os.path.dirname(settings_file), exist_ok=True)
    settings = {}

if 'hooks' not in settings:
    settings['hooks'] = {}

hooks = settings['hooks']
changed = False

# PermissionRequest hook
perm_hook = {
    'hooks': [{
        'type': 'command',
        'command': gate_cmd,
        'timeout': 600,
    }]
}
if 'PermissionRequest' not in hooks:
    hooks['PermissionRequest'] = [perm_hook]
    changed = True
else:
    # Check if our hook command is already present
    existing_cmds = [
        h.get('command', '')
        for entry in hooks['PermissionRequest']
        for h in entry.get('hooks', [])
    ]
    if gate_cmd not in existing_cmds:
        hooks['PermissionRequest'].append(perm_hook)
        changed = True

# SessionEnd cleanup hook
cleanup_cmd = 'rm -f /tmp/imessage-notify-phone-mode'
cleanup_hook = {
    'hooks': [{
        'type': 'command',
        'command': cleanup_cmd,
        'timeout': 5,
    }]
}
for event in ('SessionEnd', 'SessionStart'):
    if event not in hooks:
        hooks[event] = [cleanup_hook]
        changed = True
    else:
        existing_cmds = [
            h.get('command', '')
            for entry in hooks[event]
            for h in entry.get('hooks', [])
        ]
        if cleanup_cmd not in existing_cmds:
            hooks[event].append(cleanup_hook)
            changed = True

if changed:
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)
        f.write('\n')
    print('  ✓ Hooks configured (PermissionRequest, SessionEnd, SessionStart)')
else:
    print('  (hooks already configured)')
" "$settings_file" "$gate_cmd"
}

# =============================================================================
# Main
# =============================================================================

echo "Setting up iMessage notifications for Claude Code..."
echo ""

# --- Parse arguments ---
POSITIONAL_RECIPIENT=""
ALIASES_ARG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --aliases)
      if [ $# -lt 2 ]; then
        echo "ERROR: --aliases requires a value (space-separated addresses)" >&2
        exit 1
      fi
      ALIASES_ARG="$2"
      shift 2
      ;;
    *)
      POSITIONAL_RECIPIENT="$1"
      shift
      ;;
  esac
done

# --- Step 0: Configure RECIPIENT if phone/email argument provided ---
if [ -n "$POSITIONAL_RECIPIENT" ]; then
  input="$POSITIONAL_RECIPIENT"

  # Check if it looks like an email
  if [[ "$input" == *@* ]]; then
    recipient="$input"
    echo "Configuring recipient (email): ${recipient}"
    configure_recipient "$recipient"
  else
    # Treat as phone number — normalize it
    recipient="$(normalize_phone "$input")"
    if [ -z "$recipient" ]; then
      echo "ERROR: Could not parse phone number: ${input}" >&2
      echo "" >&2
      echo "Accepted formats:" >&2
      echo "  +13522339160        (with country code)" >&2
      echo "  1-352-233-9160      (with dashes)" >&2
      echo "  (352) 233-9160      (with parens)" >&2
      echo "  352-233-9160        (without country code)" >&2
      echo "  3522339160          (digits only)" >&2
      echo "  your.email@icloud.com  (Apple ID email)" >&2
      exit 1
    fi
    echo "Configuring recipient (phone): ${recipient}"
    configure_recipient "$recipient"
  fi
  echo ""
fi

# --- Step 0b: Configure RECIPIENT_ALIASES if --aliases provided ---
if [ -n "$ALIASES_ARG" ]; then
  configure_aliases "$ALIASES_ARG"
  echo ""
fi

# --- Step 1: Current repo's local settings ---
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
local_settings="${repo_root}/.claude/settings.local.json"

echo "Repo: ${repo_root}"
echo "Local settings: ${local_settings}"
inject_permissions "$local_settings"
echo ""

# --- Step 2: Global settings ---
global_settings="${HOME}/.claude/settings.json"

echo "Global settings: ${global_settings}"
inject_permissions "$global_settings"
echo ""

# --- Step 3: Inject hooks into global settings ---
echo "Hooks: ${global_settings}"
inject_hooks "$global_settings" "${ABS_SKILL}/permission_gate.sh"
echo ""

# --- Step 4: Ensure scripts are executable ---
if [ -x "$SKILL_DIR/send.sh" ] && [ -x "$SKILL_DIR/notify.sh" ] && [ -x "$SKILL_DIR/read.sh" ]; then
    echo "All scripts are executable."
else
    echo "Making scripts executable..."
    chmod +x "$SKILL_DIR"/*.sh
    echo "Scripts are now executable."
fi

echo ""
echo "Done. iMessage commands will no longer require IDE approval in this repo."
echo ""
echo "To test: ~/.claude/skills/imessage-notify/send.sh \"Test message\""