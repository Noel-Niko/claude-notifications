# iMessage Notifications - Quick Start

Get phone approvals working in 5 minutes.

## Installation

```bash
git clone https://github.com/wwg-internal/claude-notifications.git
cd claude-notifications
./install.sh
```

Or non-interactive:
```bash
./install.sh --phone +15551234567
```

The installer will:
1. Check prerequisites (macOS, Messages.app, sqlite3, python3)
2. Prompt for your phone number (or use `--phone`)
3. Copy scripts to `~/.claude/skills/imessage-notify/`
4. Configure permissions and Claude Code hooks automatically
5. Check Full Disk Access
6. Send a verification test message
7. Update `~/.claude/CLAUDE.md` with iMessage instructions

## Post-Install: Grant Full Disk Access

If the installer warns about FDA:

1. System Settings > Privacy & Security > Full Disk Access
2. Add your terminal app (PyCharm, VS Code, iTerm, Terminal, Cursor, Warp)
3. Toggle ON
4. **Quit and restart your terminal app completely**

```bash
# Verify FDA
~/.claude/skills/imessage-notify/check_fda.sh
```

## Post-Install: Create iMessage Chat

Open Messages app and send yourself a test message to create the conversation.

## Verify It Works

### Test 1: Send a message
```bash
~/.claude/skills/imessage-notify/send.sh "Test message"
```
You should receive this on your phone within 1-2 seconds.

### Test 2: Send and wait for reply
```bash
reply=$(~/.claude/skills/imessage-notify/notify.sh "Reply with TEST" 60 10)
echo "You replied: $reply"
```
Reply from your phone, should echo your reply.

If both work, setup is complete!

## Per-Repo Setup

For each new repo where you want phone mode, run:
```bash
cd /path/to/your/repo
~/.claude/skills/imessage-notify/whitelist_commands.sh
```

This injects permission entries so commands don't require IDE approval.

## Usage in Claude Code

**IDE mode (default):**
- Approvals show in IDE
- No phone messages (unless status updates)

**Phone mode (multi-step tasks):**
- Messages arrive on your phone immediately
- Reply from phone
- NO IDE interruption during phone mode

**Mode switching:**
- Say "switch to iMessage" in IDE > switches to phone mode
- Text "switch to IDE" to phone > switches to IDE mode

### First use: Command approval

If you ran `./install.sh`, commands are pre-approved. If you still see "Do you want to proceed?", click **"Yes"** -- it will be remembered. Re-run `whitelist_commands.sh` from the repo to fix permanently.

## Updating

```bash
cd claude-notifications
git pull
./install.sh
```

The installer is idempotent -- it detects your existing RECIPIENT and offers to keep it.

## Troubleshooting

### Messages not arriving
1. Check Messages app is running and signed in
2. Verify Full Disk Access: `~/.claude/skills/imessage-notify/check_fda.sh`
3. Test manually: `~/.claude/skills/imessage-notify/send.sh "test"`

### "Do you want to proceed?" keeps appearing
Re-run the whitelist script from inside the affected repo:
```bash
cd /path/to/your/repo
~/.claude/skills/imessage-notify/whitelist_commands.sh
```

## Full Documentation

- **Setup Guide:** `docs/setup.md` - Comprehensive installation instructions
- **Demo:** `docs/demo.md` - Full feature demo walkthrough
- **Skill Reference:** `src/imessage-notify/SKILL.md` - Technical details