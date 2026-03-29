#!/usr/bin/env bash
# install.sh — One-command installer for claude-notifications
#
# Usage:
#   ./install.sh                       # Interactive: prompts for phone number
#   ./install.sh --phone +15551234567  # Non-interactive: uses provided number
#   ./install.sh --phone user@icloud.com  # Non-interactive: uses email
#   ./install.sh --help                # Print usage
#
# Exit codes:
#   0 — success
#   1 — prerequisite check failed
#   2 — user cancelled

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="${SCRIPT_DIR}/src/imessage-notify"
INSTALL_DIR="${HOME}/.claude/skills/imessage-notify"

# ─── Helper: normalize phone number to +1XXXXXXXXXX ───
normalize_phone() {
  local input="$1"
  local digits
  digits="$(echo "$input" | tr -cd '0-9+')"
  digits="${digits#+}"

  if [[ ${#digits} -eq 11 && "$digits" == 1* ]]; then
    echo "+${digits}"
  elif [[ ${#digits} -eq 10 ]]; then
    echo "+1${digits}"
  else
    echo ""
  fi
}

# ─── Helper: print usage ───
print_usage() {
  cat <<'USAGE'
claude-notifications installer

Usage:
  ./install.sh                          Interactive: prompts for phone number
  ./install.sh --phone +15551234567     Non-interactive: US phone number
  ./install.sh --phone user@icloud.com  Non-interactive: Apple ID email
  ./install.sh --aliases "+15551234567 user@gmail.com"  Extra iMessage identities
  ./install.sh --help                   Print this help

Accepted phone formats:
  +15551234567      (with country code)
  1-555-123-4567    (with dashes)
  (555) 123-4567    (with parens)
  555-123-4567      (without country code)
  5551234567        (digits only)
  user@icloud.com   (Apple ID email)

Aliases:
  If your phone replies from a different address than the one you send to
  (e.g., you send to your email but replies come from your phone number),
  add those alternate addresses with --aliases. Space-separated.
USAGE
}

# ─── Parse flags ───
PHONE=""
ALIASES=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --phone)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --phone requires a value" >&2
        exit 1
      fi
      PHONE="$2"
      shift 2
      ;;
    --aliases)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --aliases requires a value (space-separated addresses)" >&2
        exit 1
      fi
      ALIASES="$2"
      shift 2
      ;;
    --help|-h)
      print_usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown option: $1" >&2
      print_usage
      exit 1
      ;;
  esac
done

echo "╔══════════════════════════════════════════════════════╗"
echo "║       claude-notifications installer                ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ─── Step 1: Check prerequisites ───
echo "Checking prerequisites..."

# macOS check
if [[ "$(uname)" != "Darwin" ]]; then
  echo "ERROR: This tool requires macOS. Detected: $(uname)" >&2
  exit 1
fi
echo "  ✓ macOS detected"

# Messages.app + iMessage activation check
imessage_check_exit=0
"${SRC_DIR}/check_imessage.sh" 2>/dev/null || imessage_check_exit=$?

if [[ $imessage_check_exit -eq 1 ]]; then
  echo "  ✗ Messages.app not found" >&2
  echo "  Run: ${SRC_DIR}/check_imessage.sh for details." >&2
  exit 1
elif [[ $imessage_check_exit -eq 2 ]]; then
  echo "  ✓ Messages.app found"
  echo "  ⚠ iMessage may not be activated. Installation will continue."
  echo "    Run: ${SRC_DIR}/check_imessage.sh for setup instructions."
elif [[ $imessage_check_exit -eq 0 ]]; then
  echo "  ✓ Messages.app found"
  echo "  ✓ iMessage is activated"
fi

# sqlite3 check
if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "ERROR: sqlite3 is required but not found" >&2
  exit 1
fi
echo "  ✓ sqlite3 available"

# python3 check
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required but not found" >&2
  exit 1
fi
echo "  ✓ python3 available"

# jq check (warning only — only needed for hook_notify.sh)
if ! command -v jq >/dev/null 2>&1; then
  echo "  ⚠ jq not found (optional — only needed for hook_notify.sh)"
else
  echo "  ✓ jq available (optional)"
fi

# Source scripts check
if [[ ! -d "$SRC_DIR" ]]; then
  echo "ERROR: Source scripts not found at ${SRC_DIR}" >&2
  echo "Make sure you're running this from the claude-notifications repo root." >&2
  exit 1
fi
echo "  ✓ Source scripts found"

echo ""

# ─── Step 1b: Add claude-notifications/ to parent repo's .gitignore ───
parent_git_root="$(cd "$SCRIPT_DIR/.." && git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "$parent_git_root" ]]; then
  parent_gitignore="${parent_git_root}/.gitignore"
  if [[ -f "$parent_gitignore" ]]; then
    if ! grep -qxF "claude-notifications/" "$parent_gitignore"; then
      printf '\n# Claude notifications (cloned installer)\nclaude-notifications/\n' >> "$parent_gitignore"
      echo "  ✓ Added claude-notifications/ to ${parent_gitignore}"
    else
      echo "  ✓ claude-notifications/ already in ${parent_gitignore}"
    fi
  else
    printf '# Claude notifications (cloned installer)\nclaude-notifications/\n' > "$parent_gitignore"
    echo "  ✓ Created ${parent_gitignore} with claude-notifications/"
  fi
  echo ""
fi

# ─── Step 2: Detect existing installation ───
EXISTING_RECIPIENT=""
EXISTING_ALIASES=""
if [[ -f "${INSTALL_DIR}/send.sh" ]]; then
  EXISTING_RECIPIENT="$(grep '^RECIPIENT=' "${INSTALL_DIR}/send.sh" 2>/dev/null | head -1 | sed 's/RECIPIENT="//' | sed 's/"$//' || true)"
fi
if [[ -f "${INSTALL_DIR}/read.sh" ]]; then
  EXISTING_ALIASES="$(grep '^RECIPIENT_ALIASES=' "${INSTALL_DIR}/read.sh" 2>/dev/null | head -1 | sed 's/RECIPIENT_ALIASES="//' | sed 's/"$//' || true)"
fi

if [[ -n "$EXISTING_RECIPIENT" && "$EXISTING_RECIPIENT" != "CHANGE_ME" ]]; then
  echo "Existing installation detected."
  echo "  Current RECIPIENT: ${EXISTING_RECIPIENT}"
  if [[ -n "$EXISTING_ALIASES" ]]; then
    echo "  Current ALIASES:   ${EXISTING_ALIASES}"
  fi

  if [[ -z "$PHONE" ]]; then
    echo ""
    read -p "Keep current recipient? [Y/n] " keep_choice
    if [[ "$(echo "$keep_choice" | tr '[:upper:]' '[:lower:]')" == "n" ]]; then
      EXISTING_RECIPIENT=""
      EXISTING_ALIASES=""
    else
      PHONE="$EXISTING_RECIPIENT"
      if [[ -z "$ALIASES" && -n "$EXISTING_ALIASES" ]]; then
        ALIASES="$EXISTING_ALIASES"
      fi
      echo "  Keeping existing recipient."
    fi
  fi
  echo ""
fi

# ─── Step 3: Get phone number ───
if [[ -z "$PHONE" ]]; then
  echo "Enter your phone number or Apple ID email for iMessage notifications."
  echo ""
  echo "Accepted formats:"
  echo "  +15551234567      (with country code)"
  echo "  1-555-123-4567    (with dashes)"
  echo "  (555) 123-4567    (with parens)"
  echo "  555-123-4567      (without country code)"
  echo "  5551234567        (digits only)"
  echo "  user@icloud.com   (Apple ID email)"
  echo ""

  while true; do
    read -p "Phone number or email: " phone_input

    if [[ -z "$phone_input" ]]; then
      echo "ERROR: Phone number or email is required. Ctrl+C to cancel." >&2
      continue
    fi

    # Check if it's an email
    if [[ "$phone_input" == *@* ]]; then
      PHONE="$phone_input"
      break
    fi

    # Normalize phone number
    normalized="$(normalize_phone "$phone_input")"
    if [[ -z "$normalized" ]]; then
      echo "ERROR: Could not parse phone number: ${phone_input}" >&2
      echo "Please try again with one of the formats shown above." >&2
      continue
    fi

    PHONE="$normalized"
    break
  done
  echo ""
fi

# Normalize if it's a phone number passed via --phone
if [[ "$PHONE" != *@* && "$PHONE" != "$EXISTING_RECIPIENT" ]]; then
  normalized="$(normalize_phone "$PHONE")"
  if [[ -z "$normalized" ]]; then
    echo "ERROR: Could not parse phone number: ${PHONE}" >&2
    echo "Run './install.sh --help' for accepted formats." >&2
    exit 1
  fi
  PHONE="$normalized"
fi

echo "Recipient: ${PHONE}"
echo ""

# ─── Step 3b: Get aliases (additional iMessage identities) ───
if [[ -z "$ALIASES" ]]; then
  # Attempt auto-detection from chat.db (requires FDA, may fail)
  detected_aliases=""
  if [[ -r "${HOME}/Library/Messages/chat.db" ]]; then
    # Query for other handles linked to the same person via person_centric_id (Ventura+)
    detected_aliases="$(sqlite3 "${HOME}/Library/Messages/chat.db" "
      SELECT DISTINCT h2.id
      FROM handle h1
      JOIN handle h2 ON h1.person_centric_id = h2.person_centric_id
      WHERE h1.id = '${PHONE}'
        AND h2.id != '${PHONE}'
        AND h1.person_centric_id IS NOT NULL
        AND h1.person_centric_id != '';
    " 2>/dev/null | tr '\n' ' ' | sed 's/ $//' || true)"
  fi

  if [[ -n "$detected_aliases" ]]; then
    echo "Auto-detected other iMessage identities linked to ${PHONE}:"
    for alias in $detected_aliases; do
      echo "  - ${alias}"
    done
    echo ""
    read -p "Use these as reply aliases? [Y/n] " use_detected
    if [[ "$(echo "$use_detected" | tr '[:upper:]' '[:lower:]')" != "n" ]]; then
      ALIASES="$detected_aliases"
    fi
  fi

  if [[ -z "$ALIASES" ]]; then
    echo "When you reply from your phone, the reply may come from a different"
    echo "iMessage address (e.g., your phone number instead of your email)."
    echo ""
    echo "STRONGLY RECOMMENDED: Enter any additional iMessage addresses such as the apple account email (space-separated) associated with the phone number,"
    echo "or press Enter to skip."
    if [[ -n "$EXISTING_ALIASES" ]]; then
      echo "  Previous aliases: ${EXISTING_ALIASES}"
    fi
    read -p "Aliases: " aliases_input
    ALIASES="${aliases_input:-${EXISTING_ALIASES}}"
  fi

  if [[ -n "$ALIASES" ]]; then
    echo "  Aliases: ${ALIASES}"
  else
    echo "  No aliases configured (reply must come from ${PHONE})."
  fi
  echo ""
fi

# ─── Step 4: Copy scripts ───
echo "Installing scripts to ${INSTALL_DIR}..."
mkdir -p "$INSTALL_DIR"

# Copy all .sh and .md files from source
for f in "${SRC_DIR}"/*.sh "${SRC_DIR}"/*.md; do
  if [[ -f "$f" ]]; then
    cp "$f" "$INSTALL_DIR/"
  fi
done
echo "  ✓ Scripts copied"

# ─── Step 5: Make executable ───
chmod +x "${INSTALL_DIR}"/*.sh
echo "  ✓ Scripts made executable"

# ─── Step 6: Configure RECIPIENT + permissions ───
echo ""
echo "Configuring recipient and permissions..."
if [[ -n "$ALIASES" ]]; then
  "${INSTALL_DIR}/whitelist_commands.sh" "$PHONE" --aliases "$ALIASES"
else
  "${INSTALL_DIR}/whitelist_commands.sh" "$PHONE"
fi

# ─── Step 7: Write version stamp ───
version="$(git -C "$SCRIPT_DIR" describe --tags --always 2>/dev/null || echo "unknown")"
echo "$version" > "${INSTALL_DIR}/.version"
echo ""
echo "  Version: ${version}"

# ─── Step 8: Check FDA ───
echo ""
echo "Checking Full Disk Access..."
if "${INSTALL_DIR}/check_fda.sh" 2>/dev/null; then
  echo "  ✓ Full Disk Access is granted"
else
  echo ""
  echo "  ⚠ Full Disk Access is NOT granted."
  echo "  send.sh will work without FDA, but read.sh and notify.sh need it"
  echo "  to read replies from chat.db."
  echo ""
  echo "  To grant FDA, run:"
  echo "    ${INSTALL_DIR}/check_fda.sh"
  echo "  and follow the instructions."
fi

# ─── Step 9: Remind about iMessage conversation ───
echo ""
echo "IMPORTANT: You must have an existing iMessage conversation with ${PHONE}."
echo "If you haven't already, open Messages.app and send yourself a test message."

# ─── Step 10: Verification test ───
echo ""
if [[ $imessage_check_exit -eq 2 ]]; then
  echo "Skipping verification test — iMessage is not activated."
  echo ""
  echo "  To complete setup:"
  echo "  1. Open Messages.app > Settings > iMessage > Sign in with Apple ID"
  echo "  2. Send yourself a test message to ${PHONE}"
  echo "  3. Verify with: ${INSTALL_DIR}/send.sh \"Hello\""
  echo "  4. Check status: ${INSTALL_DIR}/check_imessage.sh"
else
  echo "Running verification test..."
  if "${INSTALL_DIR}/send.sh" "Installation test from claude-notifications" >/dev/null 2>&1; then
    echo "  ✓ Test message sent successfully! Check your phone."
  else
    echo "  ⚠ Verification test failed. Possible causes:"
    echo "    - iMessage is not activated (run: ${INSTALL_DIR}/check_imessage.sh)"
    echo "    - Messages.app is not running"
    echo "    - No existing conversation with ${PHONE}"
    echo "    - Full Disk Access not granted (run: ${INSTALL_DIR}/check_fda.sh)"
    echo "  You can test manually: ${INSTALL_DIR}/send.sh \"Hello\""
  fi
fi

# ─── Step 11: Update ~/.claude/CLAUDE.md ───
CLAUDE_MD="${HOME}/.claude/CLAUDE.md"

# ── 11a: Post-compact rule (prepend to top if missing) ──
POST_COMPACT_MARKER="CRITICAL — POST-COMPACT RULE"
POST_COMPACT_BLOCK='> **CRITICAL — POST-COMPACT RULE:** After every `/compact`, you MUST re-read this file (`~/.claude/CLAUDE.md`) in full using the Read tool **before** doing anything else. Do not rely on the compacted summary for these rules — the summary may omit or simplify critical constraints. Re-reading ensures no instructions are lost. This rule itself must be preserved in the compact summary so it triggers the re-read.'

mkdir -p "$(dirname "$CLAUDE_MD")"

if [[ -f "$CLAUDE_MD" ]] && grep -qF "$POST_COMPACT_MARKER" "$CLAUDE_MD"; then
  echo "  ✓ ~/.claude/CLAUDE.md already contains post-compact rule"
else
  if [[ -f "$CLAUDE_MD" ]] && [[ -s "$CLAUDE_MD" ]]; then
    # Prepend to existing file so the rule appears first
    tmp_claude="$(mktemp)"
    printf '%s\n\n' "$POST_COMPACT_BLOCK" | cat - "$CLAUDE_MD" > "$tmp_claude"
    mv "$tmp_claude" "$CLAUDE_MD"
  else
    printf '%s\n' "$POST_COMPACT_BLOCK" > "$CLAUDE_MD"
  fi
  echo "  ✓ Post-compact rule prepended to ~/.claude/CLAUDE.md"
fi

# ── 11b: iMessage Notifications block (append if missing) ──
MARKER="## iMessage Notifications (MANDATORY)"

IMESSAGE_BLOCK='## iMessage Notifications (MANDATORY)

**CRITICAL — Read `~/.claude/skills/imessage-notify/SKILL.md` BEFORE producing any output.** This file defines the full communication protocol. If you skip it, you will use the wrong output channel and the user will not see your work. If scripts fail, run `~/.claude/skills/imessage-notify/check_fda.sh` and relay setup instructions.

**Two modes:** IDE mode (default) and Phone mode.

**Automatic phone mode triggers — no confirmation needed:**
If the user mentions "iMessage", "phone", "away from computer", or "away from the compute" anywhere in their message, **immediately switch to phone mode**. Do not ask for confirmation. Do not offer — just switch. Also switch if the user'\''s message contains contextual signals: `install.sh` output, phone demo replies, or references to the iMessage system being set up. When in doubt, switch — a false positive (one iMessage) costs less than a false negative (invisible IDE output).

**Manual switches:**
- User says "switch to iMessage" → phone mode immediately
- User texts "switch to IDE" (via iMessage reply) → IDE mode immediately

**After /compact:** Re-read this section and SKILL.md. If you were in phone mode before compaction, send a confirmation via `notify.sh`: "Session compacted. Still in phone mode. Reply OK to confirm." If no reply context exists, default to IDE mode.

**IDE mode behavior:**
- Use `AskUserQuestion` or `ExitPlanMode` for approvals
- Optionally use `send.sh` for fire-and-forget status updates

**Phone mode behavior — IDE is NOT a communication channel:**
- Use `notify.sh` for ALL approvals — never show IDE prompts
- Use `send.sh` for fire-and-forget status updates
- Check every reply for "switch to IDE"
- Include full context in messages (the user only sees their phone)
- IDE text: ONLY brief trace lines ("Sent via iMessage.", "Running tests.")
- Do NOT write summaries, tables, or reports to IDE in phone mode

**Sending messages (IMPORTANT — use file mode for multiline):**
- **Short single-line**: `~/.claude/skills/imessage-notify/notify.sh "Short msg" 600 10`
- **Multiline or long messages**: Use the Write tool to create a temp file, then pass it with `-f`:
  1. Write message to `/tmp/imessage-notify-msg-{uuid}.txt` using the Write tool
  2. Run: `~/.claude/skills/imessage-notify/notify.sh -f /tmp/imessage-notify-msg-{uuid}.txt 600 10`
  - The `-f` flag reads the file and deletes it after sending
  - This avoids CLI permission prompts that block multiline Bash commands
- **Fire-and-forget**: Same patterns but with `send.sh` instead of `notify.sh`'

if [[ -f "$CLAUDE_MD" ]] && grep -qF "$MARKER" "$CLAUDE_MD"; then
  # Delete from marker to EOF, then append the (possibly updated) block
  # This works because the iMessage block is always the last content in the file.
  LINE_NUM=$(grep -nF "$MARKER" "$CLAUDE_MD" | head -1 | cut -d: -f1)
  # Keep everything before the marker (strip trailing blank lines)
  head -n $(( LINE_NUM - 1 )) "$CLAUDE_MD" | perl -0777 -pe 's/\s+\z/\n/' > "${CLAUDE_MD}.tmp"
  mv "${CLAUDE_MD}.tmp" "$CLAUDE_MD"
  # Append updated block
  printf '\n\n%s\n' "$IMESSAGE_BLOCK" >> "$CLAUDE_MD"
  echo "  ✓ iMessage Notifications block updated in ~/.claude/CLAUDE.md"
else
  # First install — append with a blank line separator
  if [[ -f "$CLAUDE_MD" ]] && [[ -s "$CLAUDE_MD" ]]; then
    printf '\n\n%s\n' "$IMESSAGE_BLOCK" >> "$CLAUDE_MD"
  else
    printf '%s\n' "$IMESSAGE_BLOCK" > "$CLAUDE_MD"
  fi
  echo "  ✓ iMessage Notifications block added to ~/.claude/CLAUDE.md"
fi

echo ""
echo "════════════════════════════════════════════════════════"
echo "  Installation complete!"
echo "════════════════════════════════════════════════════════"
echo ""
echo "Optional: To enable automatic hook notifications, add this to"
echo "your ~/.claude/settings.json under \"hooks\":"
echo ""
cat <<'HOOKSNIPPET'
{
  "hooks": {
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/skills/imessage-notify/hook_notify.sh"
          }
        ]
      }
    ]
  }
}
HOOKSNIPPET
echo ""
echo "To update later: git pull && ./install.sh"
echo ""

# ─── Step 12: Offer interactive demo ───
echo ""
if [[ $imessage_check_exit -eq 2 ]]; then
  echo "Skipping demo — iMessage is not activated."
  echo "After activating iMessage, reinstall with: ./install.sh"
  echo ""
  exit 0
fi

read -p "Would you like to run a quick interactive demo? [y/N] " run_demo

run_demo_lower="$(echo "$run_demo" | tr '[:upper:]' '[:lower:]')"
if [[ "$run_demo_lower" == "y" || "$run_demo_lower" == "yes" ]]; then
  echo ""
  echo "╔══════════════════════════════════════════════════════╗"
  echo "║              Interactive Demo                        ║"
  echo "╚══════════════════════════════════════════════════════╝"
  echo ""

  # Demo Step 1: Fire-and-forget send
  echo "── Demo 1/3: Fire-and-forget message (send.sh) ──"
  echo ""
  echo "Sending a status notification to your phone..."
  echo "(This is send.sh — fire-and-forget, no reply expected)"
  echo ""
  if "${INSTALL_DIR}/send.sh" "Demo 1/3: This is a fire-and-forget notification. No reply needed." >/dev/null 2>&1; then
    echo "  ✓ Message sent! Check your phone."
  else
    echo "  ✗ Failed to send. Check Messages.app is running."
    echo "  Skipping remaining demo steps."
    exit 0
  fi

  echo ""
  read -p "Press Enter when you've seen the message on your phone..."
  echo ""

  # Demo Step 2: Two-way communication with notify.sh
  echo "── Demo 2/3: Two-way communication (notify.sh) ──"
  echo ""
  echo "Sending a question to your phone and waiting for your reply..."
  echo "(This is notify.sh — it sends a message and polls for your reply)"
  echo ""
  reply="$("${INSTALL_DIR}/notify.sh" "Demo 2/3: This is a two-way message. Reply with any word to continue the demo." 120 5 2>&1 | tail -1)"

  if [[ $? -eq 0 && -n "$reply" ]]; then
    echo "  ✓ Received your reply: \"${reply}\""
  else
    echo "  ✗ Timed out or failed. Make sure you replied to the iMessage."
    echo "  Skipping remaining demo steps."
    exit 0
  fi

  echo ""

  # Demo Step 3: Explain phone mode
  echo "── Demo 3/3: Phone mode explained ──"
  echo ""
  "${INSTALL_DIR}/send.sh" "Demo 3/3: Demo complete! In real usage, Claude Code uses send.sh for status updates and notify.sh for approvals. Say 'switch to iMessage' in any Claude session to enable phone mode." >/dev/null 2>&1
  echo "  ✓ Final demo message sent to your phone."
  echo ""
  echo "Demo complete! Here's how it works in practice:"
  echo ""
  echo "  send.sh   → Fire-and-forget notifications (build passed, task done)"
  echo "  notify.sh → Two-way approval (deploy to prod? reply YES/NO)"
  echo ""
  echo "  In Claude Code, say 'switch to iMessage' to enable phone mode."
  echo "  Claude will use notify.sh for all approvals instead of IDE prompts."
  echo "  Reply 'switch to IDE' on your phone to switch back."
  echo ""
fi