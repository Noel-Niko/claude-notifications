#!/usr/bin/env bash
# uninstall.sh — Remove claude-notifications skill files, permissions, and config
#
# What it does:
#   1. Removes ~/.claude/skills/imessage-notify/ directory
#   2. Removes iMessage permission entries from ~/.claude/settings.json (global)
#   2b. Removes iMessage hooks from ~/.claude/settings.json (global)
#   3. Removes installer blocks from ~/.claude/CLAUDE.md
#   4. Removes claude-notifications/ entry from parent repo's .gitignore
#   5. Removes runtime pending directory and phone mode flag
#   6. Prints note about local repo settings (or cleans them with --all)
#
# Usage:
#   ./uninstall.sh         # Standard cleanup
#   ./uninstall.sh --all   # Also clean parent repo's local settings

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="${HOME}/.claude/skills/imessage-notify"
GLOBAL_SETTINGS="${HOME}/.claude/settings.json"
CLAUDE_MD="${HOME}/.claude/CLAUDE.md"
PENDING_DIR="${PENDING_DIR:-/tmp/imessage-notify-pending}"

# Permission patterns to remove (tilde + absolute forms)
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

# ─── Parse flags ───
ALL_FLAG=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)
      ALL_FLAG=true
      shift
      ;;
    *)
      echo "ERROR: Unknown option: $1" >&2
      echo "Usage: ./uninstall.sh [--all]" >&2
      exit 1
      ;;
  esac
done

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

# ─── Step 2b: Remove hooks from global settings ───
if [[ -f "$GLOBAL_SETTINGS" ]]; then
  echo ""
  echo "Cleaning hooks from global settings: ${GLOBAL_SETTINGS}"

  python3 -c "
import json, sys

settings_file = sys.argv[1]

with open(settings_file, 'r') as f:
    settings = json.load(f)

if 'hooks' not in settings:
    print('  No hooks section found')
    sys.exit(0)

hooks = settings['hooks']
changed = False

# Remove PermissionRequest hooks containing permission_gate.sh
if 'PermissionRequest' in hooks:
    before = len(hooks['PermissionRequest'])
    hooks['PermissionRequest'] = [
        entry for entry in hooks['PermissionRequest']
        if not any(
            'permission_gate.sh' in h.get('command', '')
            for h in entry.get('hooks', [])
        )
    ]
    if not hooks['PermissionRequest']:
        del hooks['PermissionRequest']
    if len(hooks.get('PermissionRequest', [])) < before:
        changed = True

# Remove SessionEnd/SessionStart cleanup hooks
cleanup_cmd = 'rm -f /tmp/imessage-notify-phone-mode'
for event in ('SessionEnd', 'SessionStart'):
    if event in hooks:
        before = len(hooks[event])
        hooks[event] = [
            entry for entry in hooks[event]
            if not any(
                h.get('command', '') == cleanup_cmd
                for h in entry.get('hooks', [])
            )
        ]
        if not hooks[event]:
            del hooks[event]
        if len(hooks.get(event, [])) < before:
            changed = True

# Remove empty hooks section
if not hooks:
    del settings['hooks']
    changed = True

if changed:
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)
        f.write('\n')
    print('  ✓ Removed iMessage hooks')
else:
    print('  No matching hooks found')
" "$GLOBAL_SETTINGS"
fi

# ─── Step 3: Remove installer blocks from CLAUDE.md ───
echo ""
if [[ -f "$CLAUDE_MD" ]]; then
  echo "Cleaning CLAUDE.md: ${CLAUDE_MD}"

  python3 -c "
import os, re, sys

claude_md = sys.argv[1]

with open(claude_md, 'r') as f:
    content = f.read()

# Remove post-compact rule line and any immediately following blank lines
content = re.sub(
    r'^> \*\*CRITICAL — POST-COMPACT RULE:\*\*[^\n]*\n(\n)*',
    '',
    content,
    flags=re.MULTILINE,
)

# Remove iMessage Notifications block (from header to EOF)
# The block is always appended at the end by install.sh
content = re.sub(
    r'\n*## iMessage Notifications \(MANDATORY\).*',
    '',
    content,
    flags=re.DOTALL,
)

content = content.strip()

if content:
    with open(claude_md, 'w') as f:
        f.write(content + '\n')
    print('  ✓ Removed installer blocks from CLAUDE.md')
else:
    os.remove(claude_md)
    print('  ✓ CLAUDE.md was empty after cleanup — deleted')
" "$CLAUDE_MD"
else
  echo "  - ${CLAUDE_MD} not found"
fi

# ─── Step 4: Clean parent .gitignore ───
echo ""
parent_git_root="$(cd "$SCRIPT_DIR/.." && git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "$parent_git_root" ]]; then
  parent_gitignore="${parent_git_root}/.gitignore"
  if [[ -f "$parent_gitignore" ]]; then
    python3 -c "
import os, sys

gitignore_path = sys.argv[1]

with open(gitignore_path, 'r') as f:
    lines = f.readlines()

filtered = []
skip_next = False
for line in lines:
    if skip_next:
        skip_next = False
        continue
    if line.strip() == '# Claude notifications (cloned installer)':
        skip_next = True
        continue
    if line.strip() == 'claude-notifications/':
        continue
    filtered.append(line)

content = ''.join(filtered).strip()

if content:
    with open(gitignore_path, 'w') as f:
        f.write(content + '\n')
    print(f'  ✓ Removed claude-notifications/ from {gitignore_path}')
else:
    os.remove(gitignore_path)
    print(f'  ✓ {gitignore_path} was empty after cleanup — deleted')
" "$parent_gitignore"
  else
    echo "  - Parent .gitignore not found"
  fi
else
  echo "  - No parent git repo detected"
fi

# ─── Step 5: Clean runtime artifacts ───
echo ""
if [[ -d "$PENDING_DIR" ]]; then
  rm -rf "$PENDING_DIR"
  echo "  ✓ Removed pending directory: ${PENDING_DIR}"
else
  echo "  - Pending directory not found (already clean)"
fi

PHONE_MODE_FLAG="/tmp/imessage-notify-phone-mode"
if [[ -f "$PHONE_MODE_FLAG" ]]; then
  rm -f "$PHONE_MODE_FLAG"
  echo "  ✓ Removed phone mode flag: ${PHONE_MODE_FLAG}"
fi

# ─── Step 6: Local settings ───
echo ""
if [[ "$ALL_FLAG" == "true" ]]; then
  # Auto-clean parent repo's local settings
  if [[ -n "$parent_git_root" ]]; then
    local_settings="${parent_git_root}/.claude/settings.local.json"
    if [[ -f "$local_settings" ]]; then
      echo "Cleaning local settings (--all): ${local_settings}"
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
        print(f'  Removed {removed} local permission entries')
    else:
        print('  No matching local permission entries found')
else:
    print('  No permissions section found in local settings')
" "$local_settings" "${PERMISSIONS[@]}"
    else
      echo "  - ${local_settings} not found"
    fi
  else
    echo "  - No parent git repo detected for local settings cleanup"
  fi
else
  echo "Note: Per-repo .claude/settings.local.json files are NOT modified."
  echo "To clean those manually, remove these entries from each repo's"
  echo ".claude/settings.local.json permissions.allow array:"
  echo ""
  for perm in "${PERMISSIONS[@]}"; do
    echo "  ${perm}"
  done
  echo ""
  echo "Or re-run with --all to auto-clean the parent repo's local settings."
fi

echo ""
echo "Uninstall complete."
