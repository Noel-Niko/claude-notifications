# iMessage Notify — Claude Code Skill

A set of shell scripts that let Claude Code send iMessages to your phone and read your replies. This enables notifications and approval workflows when you're away from the terminal.

## How It Works

1. **Send**: `send.sh` uses AppleScript to send an iMessage tagged with the repo name and a unique request ID (e.g., `[my-repo|REQ-a1b2c3d4] Tests passed.`)
2. **Read**: `read.sh` polls macOS's `~/Library/Messages/chat.db` (SQLite) for inbound replies after the message was sent
3. **Notify**: `notify.sh` combines both — sends a message and blocks until you reply on your phone

Messages are routed so multiple Claude Code sessions (in different repos) can run simultaneously without cross-talk. Each message gets a unique ID, and replies are matched by ID first, then by timestamp for the most recent pending request.

## Prerequisites

- macOS with the Messages app signed into iMessage
- **Full Disk Access** granted to your terminal app (required to read `chat.db`)
- An existing iMessage conversation with the configured recipient

### Granting Full Disk Access

Run `check_fda.sh` to verify. If FDA is missing, it will detect your terminal app and print setup steps:

```bash
~/.claude/skills/imessage-notify/check_fda.sh
```

The general process:

1. System Settings > Privacy & Security > Full Disk Access
2. Add your terminal app (PyCharm, VS Code, iTerm, Terminal, Cursor, Warp, etc.)
3. Toggle it on
4. Restart the terminal app completely

## Usage

### Send a notification (fire and forget)

```bash
~/.claude/skills/imessage-notify/send.sh "Build succeeded. 42 tests passed."
# Output: REQ_ID=a1b2c3d4 SENT_EPOCH=1700000000
```

### Send and wait for a reply

```bash
reply=$(~/.claude/skills/imessage-notify/notify.sh "Deploy to staging? Reply YES or NO." 300 10)
echo "$reply"  # e.g., "YES"
```

Arguments: `notify.sh <message> [timeout_seconds=300] [poll_interval_seconds=10]`

### Poll for a reply (after sending separately)

```bash
~/.claude/skills/imessage-notify/read.sh <sent_epoch> [timeout=300] [poll_interval=10] [req_id]
```

## Multi-Session Routing

When multiple Claude Code sessions are waiting for replies at the same time:

- Each outbound message is tagged: `[repo-name|REQ-<id>] message`
- **To reply to a specific request**, include the ID: `a1b2c3d4 yes`
- **To reply to the most recent request**, just reply normally: `yes`

Pending requests are tracked in `/tmp/imessage-notify-pending/`. Atomic `mkdir`-based claiming prevents two sessions from grabbing the same reply.

## Files

| File | Description |
|------|-------------|
| `SKILL.md` | Instructions that Claude Code reads to know how to use the skill |
| `send.sh` | Send a tagged iMessage via AppleScript |
| `read.sh` | Poll `chat.db` for replies with ID matching and claim logic |
| `notify.sh` | Combined send + wait-for-reply |
| `check_fda.sh` | Verify Full Disk Access and print setup instructions if missing |

## Configuration

The recipient iMessage address is set in `send.sh` and `read.sh` via the `RECIPIENT` variable. To change it, update both files.

### Reply Aliases

When you reply from your phone, the reply may come from a different iMessage identity (e.g., your phone number instead of your email). `read.sh` has a `RECIPIENT_ALIASES` variable that lists additional addresses to check for replies. The SQL query uses `IN (recipient, alias1, alias2, ...)` instead of matching a single address.

Configure aliases via the installer or directly:
```bash
# Via whitelist_commands.sh:
~/.claude/skills/imessage-notify/whitelist_commands.sh nnosse@wgu.edu --aliases "+13522339160 noelnosse@gmail.com"

# Or edit read.sh directly:
RECIPIENT_ALIASES="+13522339160 noelnosse@gmail.com"
```