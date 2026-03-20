#!/usr/bin/env bash
# uninstall.sh — Remove claude-notifications skill files and global permissions
#
# What it does:
#   1. Removes ~/.claude/skills/imessage-notify/ directory
#   2. Removes iMessage permission entries from ~/.claude/settings.json (global)
#   3. Prints note about local repo settings (not modified)

set -euo pipefail

INSTALL_DIR="${HOME}/.claude/skills/imessage-notify"
GLOBAL_SETTINGS="${HOME}/.claude/settings.json"

PERMISSIONS=(
  'Bash(~/.claude/skills/imessage-notify/notify.sh *)'
  'Bash(~/.claude/skills/imessage-notify/send.sh *)'
  'Bash(~/.claude/skills/imessage-notify/read.sh *)'
  'Bash(~/.claude/skills/imessage-notify/check_fda.sh)'
)

echo "Uninstalling claude-notifications..."
echo ""

# ─── Step 1: Remove skill directory ───
if [[ -d "$INSTALL_DIR" ]]; then
  rm -rf "$INSTALL_DIR"
  echo "  ✓ Removed ${INSTALL_DIR}"
else
  echo "  - ${INSTALL_DIR} not found (already removed)"
fi

# ─── Step 2: Remove permissions from global settings ───
if [[ -f "$GLOBAL_SETTINGS" ]]; then
  echo ""
  echo "Cleaning global settings: ${GLOBAL_SETTINGS}"

  python3 -c "
import json, sys

settings_file = sys.argv[1]
permissions_to_remove = set(sys.argv[2:])

with open(settings_file, 'r') as f:
    settings = json.load(f)

if 'permissions' in settings and 'allow' in settings['permissions']:
    before = len(settings['permissions']['allow'])
    settings['permissions']['allow'] = [
        p for p in settings['permissions']['allow']
        if p not in permissions_to_remove
    ]
    after = len(settings['permissions']['allow'])
    removed = before - after

    if removed > 0:
        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=2)
            f.write('\n')
        print(f'  Removed {removed} permission entries')
    else:
        print('  No matching permission entries found')
else:
    print('  No permissions section found')
" "$GLOBAL_SETTINGS" "${PERMISSIONS[@]}"
else
  echo "  - ${GLOBAL_SETTINGS} not found"
fi

# ─── Step 3: Note about local settings ───
echo ""
echo "Note: Per-repo .claude/settings.local.json files are NOT modified."
echo "To clean those manually, remove these entries from each repo's"
echo ".claude/settings.local.json permissions.allow array:"
echo ""
for perm in "${PERMISSIONS[@]}"; do
  echo "  ${perm}"
done

echo ""
echo "Uninstall complete."