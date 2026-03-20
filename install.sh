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
  ./install.sh --help                   Print this help

Accepted phone formats:
  +15551234567      (with country code)
  1-555-123-4567    (with dashes)
  (555) 123-4567    (with parens)
  555-123-4567      (without country code)
  5551234567        (digits only)
  user@icloud.com   (Apple ID email)
USAGE
}

# ─── Parse flags ───
PHONE=""
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

# Messages.app check
if [[ ! -d "/System/Applications/Messages.app" ]]; then
  echo "ERROR: Messages.app not found at /System/Applications/Messages.app" >&2
  exit 1
fi
echo "  ✓ Messages.app found"

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

# ─── Step 2: Detect existing installation ───
EXISTING_RECIPIENT=""
if [[ -f "${INSTALL_DIR}/send.sh" ]]; then
  EXISTING_RECIPIENT="$(grep '^RECIPIENT=' "${INSTALL_DIR}/send.sh" 2>/dev/null | head -1 | sed 's/RECIPIENT="//' | sed 's/"$//' || true)"
fi

if [[ -n "$EXISTING_RECIPIENT" && "$EXISTING_RECIPIENT" != "CHANGE_ME" ]]; then
  echo "Existing installation detected."
  echo "  Current RECIPIENT: ${EXISTING_RECIPIENT}"

  if [[ -z "$PHONE" ]]; then
    echo ""
    read -p "Keep current recipient? [Y/n] " keep_choice
    if [[ "$(echo "$keep_choice" | tr '[:upper:]' '[:lower:]')" == "n" ]]; then
      EXISTING_RECIPIENT=""
    else
      PHONE="$EXISTING_RECIPIENT"
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
"${INSTALL_DIR}/whitelist_commands.sh" "$PHONE"

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
echo "Running verification test..."
if "${INSTALL_DIR}/send.sh" "Installation test from claude-notifications" >/dev/null 2>&1; then
  echo "  ✓ Test message sent successfully! Check your phone."
else
  echo "  ⚠ Verification test failed. Check that Messages.app is running and"
  echo "  you have an existing conversation with ${PHONE}."
  echo "  You can test manually: ${INSTALL_DIR}/send.sh \"Hello\""
fi

# ─── Step 11: Update ~/.claude/CLAUDE.md ───
CLAUDE_MD="${HOME}/.claude/CLAUDE.md"
MARKER="## iMessage Notifications (MANDATORY) - Dynamic Mode Switching"

IMESSAGE_BLOCK='## iMessage Notifications (MANDATORY) - Dynamic Mode Switching

**Approval modes:**
- **IDE mode** (default): Use IDE tools (`AskUserQuestion`, `ExitPlanMode`) for approvals
- **Phone mode**: Use `notify.sh` for phone-only approvals

**Mode switching protocol:**
1. **Default**: Start in IDE mode
2. **Offer phone mode** when you detect multi-step tasks (3+ approval points):
   - Ask: "This is a multi-step task. Want to switch to phone approvals? [Yes/No]"
3. **Manual switch to phone**: When user says "switch to iMessage" anywhere
4. **Manual switch to IDE**: When user texts "switch to IDE" to phone (only works in phone mode)
5. **Track current mode**: Remember which mode you'\''re in throughout the session

**In IDE mode:**
- Use `AskUserQuestion` or `ExitPlanMode` for approvals
- Optionally use `send.sh` for fire-and-forget notifications (no reply expected)
- Watch for user saying "switch to iMessage"

**In Phone mode:**
- For short single-line messages, use argument mode:
  ```bash
  ~/.claude/skills/imessage-notify/notify.sh "Your message here" 600 10
  ```
- For long or multiline messages, use stdin mode to avoid permission prompt issues:
  ```bash
  echo "Your multiline message here" | ~/.claude/skills/imessage-notify/notify.sh - 600 10
  ```
- Same for fire-and-forget: `echo "msg" | ~/.claude/skills/imessage-notify/send.sh -`
- Check every reply for "switch to IDE" command
- If detected, switch back to IDE mode and confirm the switch
- Include full context in messages (options, questions, everything user needs)

**Command approval handling:**
- Run `~/.claude/skills/imessage-notify/whitelist_commands.sh` from each repo to pre-approve commands
- If you still see "Do you want to proceed?", click Yes once — it'\''s remembered for that session

**When in doubt:**
- For single approvals: Use IDE mode
- For 3+ step tasks: Offer phone mode
- Let user choose their preference

**Setup:**
- Read `~/.claude/skills/imessage-notify/SKILL.md` for the full protocol on first use
- If scripts fail, run `~/.claude/skills/imessage-notify/check_fda.sh` and relay setup instructions'

mkdir -p "$(dirname "$CLAUDE_MD")"

if [[ -f "$CLAUDE_MD" ]] && grep -qF "$MARKER" "$CLAUDE_MD"; then
  echo "  ✓ ~/.claude/CLAUDE.md already contains iMessage Notifications block"
else
  # Append with a blank line separator
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