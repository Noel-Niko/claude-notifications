> **FIRST USE GATE:** Before producing ANY output in this session, read this
> entire file. Do not respond to the user. Do not begin working. Do not
> produce IDE output. Finish reading first. This file governs how you
> communicate with the user. Skipping it means you will use the wrong output
> channel and the user will not see your work.

# iMessage Notification Skill

Send iMessages to the user's phone and read their replies. Use this for approvals and notifications with dynamic mode-switching between IDE and phone.

## Quick Decision Tree

```
User triggers phone mode? (keywords OR contextual signals — see below)
└─ YES → Switch to phone mode immediately (no confirmation)

In IDE mode? (default)
├─ Use AskUserQuestion / ExitPlanMode for approvals
└─ Use send.sh for optional fire-and-forget status updates

In Phone mode? (IDE is NOT a communication channel)
├─ Use notify.sh for ALL approvals
├─ Use send.sh for fire-and-forget status updates
├─ IDE text: only brief trace lines ("Sent via iMessage.", "Running tests.")
└─ Check each reply for "switch to IDE"

Status update (no reply needed)?
└─ Use send.sh (works in either mode)
```

## Mode-Switching Protocol

**Two modes:** IDE mode (default) and Phone mode.

**Automatic phone mode triggers — no confirmation needed:**

Switch to phone mode immediately (no confirmation, no offer) if ANY of these
are true:

**Keyword triggers** — the user's message contains any of:
- "iMessage", "phone", "away from computer", "away from the compute"
- "switch to iMessage", "use iMessage", "text me", "message me"

**Contextual triggers** — the user's message contains:
- Terminal output from `install.sh` or `whitelist_commands.sh` (the user
  just set up iMessage notifications — they expect phone mode)
- A phone demo reply (e.g., the user replied to a test message from their
  phone, proving they are actively on their phone)
- References to the iMessage notification system being configured or tested

**Intent rule**: If the user's actions demonstrate they are on their phone or
expect phone communication, switch to phone mode. Do not require exact keyword
matches when contextual evidence is clear.

**Manual switches:**
- User says "switch to iMessage" → phone mode immediately
- User texts "switch to IDE" (via iMessage reply) → IDE mode immediately

**Phone mode activation sequence (MANDATORY — follow every step):**

When entering phone mode, execute these steps in order:

1. Run: `touch /tmp/imessage-notify-phone-mode` (enables the permission hook)
2. If the user's message includes a task (e.g., "switch to iMessage and review
   the codebase"), begin the task and send progress via `send.sh`
3. If the user's message is ONLY about switching modes (no task), send a
   confirmation via `notify.sh` (NOT send.sh) and wait for their reply:
   `"Phone mode active. What would you like me to work on?"`
   The user's reply IS their first task — process it immediately.
4. IDE trace: "Phone mode active. Waiting for instructions via iMessage."

**CRITICAL:** Always use `notify.sh` (wait-for-reply) when you need the user's
next instruction. If you use `send.sh` (fire-and-forget) and stop, the user is
stranded on their phone with no way to give you work — they'd have to come back
to the IDE to type another message, defeating the purpose of phone mode.

**Phone mode deactivation sequence:**

When the user replies "switch to IDE" (or similar) via iMessage:

1. Run: `rm -f /tmp/imessage-notify-phone-mode` (disables the permission hook)
2. Confirm via IDE text: "Switched back to IDE mode."
3. Resume using IDE prompts for approvals.

**After /compact:** Re-read this section. If you were in phone mode before compaction, run `touch /tmp/imessage-notify-phone-mode` and send a confirmation via `notify.sh`: "Session compacted. Still in phone mode. Reply OK to confirm." If no reply context exists, run `rm -f /tmp/imessage-notify-phone-mode` and default to IDE mode.

**IDE mode behavior:**
- Use `AskUserQuestion` or `ExitPlanMode` for approvals (DO NOT use notify.sh for approvals)
- Optionally use `send.sh` for fire-and-forget status updates

**Phone mode behavior:**

In phone mode, the IDE is not a communication channel. The user is not
looking at it. All substantive output goes through iMessage only.

- Use ONLY `notify.sh` for approvals — NEVER show IDE prompts
- Use `send.sh` for fire-and-forget status updates
- NEVER use both IDE approvals and `notify.sh` for the same approval
- Check every reply for "switch to IDE" command
- If detected, run the deactivation sequence above
- Include full context in iMessages (the user only sees their phone)
- After completing a task, use `notify.sh` to ask what's next — do NOT
  stop and wait for IDE input

**IDE output rules (phone mode):**
- The ONLY text that should appear in the IDE is brief operational trace
  lines: "Sent via iMessage.", "Running tests.", "Waiting for reply."
- Do NOT write markdown tables, bullet lists, summaries, or reports to
  the IDE while in phone mode.
- Do NOT duplicate iMessage content in the IDE. If you sent it via
  `send.sh` or `notify.sh`, do not also render it as IDE text.
- On step completion: send the result via `send.sh` only. IDE trace:
  "Sent update via iMessage."
- On approval needed: use `notify.sh` only. IDE trace: "Waiting for
  reply on phone."

**On mode-switch reminder:**
If the user reminds you to use iMessage protocol:
- From the next response onward, apply all IDE output rules above.
- Run `touch /tmp/imessage-notify-phone-mode` if not already present.
- Send acknowledgment via `notify.sh` (not IDE text) and wait for their
  instruction.
- Do not simply confirm the reminder and continue writing to the IDE.

## Scripts

All scripts are located in `~/.claude/skills/imessage-notify/`.

### Send Only (no wait)

```bash
# Short single-line messages:
~/.claude/skills/imessage-notify/send.sh "Your message here"

# Multiline messages — use file mode (avoids CLI permission prompts):
# Step 1: Use the Write tool to create /tmp/imessage-notify-msg-<uuid>.txt
# Step 2: Run:
~/.claude/skills/imessage-notify/send.sh -f /tmp/imessage-notify-msg-<uuid>.txt
```

Outputs: `REQ_ID=<id> SENT_EPOCH=<epoch>`

Messages are auto-tagged with the repo name and request ID:
```
[my-repo|REQ-a1b2c3d4] Your message here
```

### Send and Wait for Reply

```bash
# Short single-line messages:
~/.claude/skills/imessage-notify/notify.sh "Your question here" [timeout_seconds] [poll_interval_seconds]

# Multiline messages — use file mode:
# Step 1: Use the Write tool to create /tmp/imessage-notify-msg-<uuid>.txt
# Step 2: Run:
~/.claude/skills/imessage-notify/notify.sh -f /tmp/imessage-notify-msg-<uuid>.txt [timeout_seconds] [poll_interval_seconds]
```

- Default timeout: 300 seconds (5 minutes)
- Default poll interval: 10 seconds
- Outputs the user's reply text on success, exits 1 on timeout

**WHY file mode?** Claude Code's permission system uses glob patterns to whitelist Bash commands. The glob `*` does not match newlines, so any multiline Bash command (heredoc, multiline echo) will trigger an IDE "Do you want to proceed?" prompt — which defeats the purpose of phone mode. The `-f` flag keeps the Bash command on a single line regardless of message length, matching the existing `notify.sh *` permission pattern.

### Read Only (poll for reply after a known send time)

```bash
~/.claude/skills/imessage-notify/read.sh <sent_epoch> [timeout_seconds] [poll_interval_seconds] [req_id]
```

`read.sh` delegates the database query to `query_messages.py`, which decodes the `attributedBody` column (Apple typedstream format) when the `text` column is NULL. This handles macOS Sequoia's inconsistent message storage transparently.

## Background Execution (IMPORTANT)

**Always use `Bash(run_in_background=true)` for notify.sh — NEVER spawn a Task sub-agent.**

`notify.sh` blocks while polling for a reply (up to 10 minutes). To keep working while waiting, use the Bash tool's `run_in_background` parameter. This runs the command in the **same session** and inherits all permissions.

**Correct — background Bash:**
```
Bash(~/.claude/skills/imessage-notify/notify.sh "Deploy? YES/NO" 600 10, run_in_background=true)
# Continue working...
# Later, check for the reply:
TaskOutput(task_id=<id>, block=false)
```

**WRONG — Task sub-agent:**
```
# DO NOT DO THIS — sub-agents have separate permission contexts and will fail:
Task(subagent_type=Bash, prompt="run notify.sh ...", run_in_background=true)
```

Sub-agents (Task tool) run as separate Claude instances with their own permission context. Even with allowlisted commands in `settings.json`, sub-agents may fail to resolve `~` in permission patterns or may lack session-scoped approvals. `Bash(run_in_background)` avoids this entirely.

**When to use which:**
- `send.sh` — Run in foreground (fast, fire-and-forget)
- `notify.sh` — Run in background via `Bash(run_in_background=true)`, check result later
- Never use `Task` sub-agents to run these scripts

## Multi-Repo / Multi-Session Support

Multiple Claude Code sessions can use this skill simultaneously without cross-talk.

### How it works

1. Each outbound message is tagged: `[repo-name|REQ-<unique-id>] message`
2. The repo name is auto-detected from git (or the current directory name)
3. Pending requests are tracked in `/tmp/imessage-notify-pending/`

### Reply routing (priority order)

1. **Explicit ID match**: If the user's reply contains the request ID (e.g., `a1b2c3d4 yes`), it is routed to that specific session. The ID prefix is stripped from the reply.
2. **Most-recent fallback**: A plain reply (e.g., just `yes`) is routed to whichever session sent the most recent pending request.

### When the user has multiple pending requests

The user will see messages like:
```
[api-server|REQ-a1b2c3d4] Deploy to staging? Reply YES or NO.
[frontend|REQ-e5f6g7h8] Run e2e tests? Reply YES or NO.
```

To reply to a specific one, include the ID:
```
a1b2c3d4 yes
```

Or just reply plainly to answer the most recent request:
```
yes
```

## Example Usage in Claude Code

### Example 1: IDE mode (default) — single approval

```
Use AskUserQuestion tool. DO NOT use notify.sh.
```

### Example 2: User says "use iMessage" — switch immediately

```
User: "Research this topic, use iMessage to communicate"
→ Immediately enter phone mode. No confirmation prompt.
→ Send first message via notify.sh.
```

### Example 3: Multiline phone mode approval (file mode)

```
1. Use Write tool to create /tmp/imessage-notify-msg-abc123.txt with the full message
2. Run: ~/.claude/skills/imessage-notify/notify.sh -f /tmp/imessage-notify-msg-abc123.txt 600 10
3. The script reads the file, sends it, deletes the temp file
```

### Example 4: Fire-and-forget status update (either mode)

```bash
~/.claude/skills/imessage-notify/send.sh "Tests passed. All 42 tests green."
```

### Example 5: Phone mode with switch-to-IDE detection

```bash
reply=$(~/.claude/skills/imessage-notify/notify.sh "Deploy to staging? YES or NO" 600 10)
# If reply contains "switch to IDE", switch back to IDE mode
```

### WRONG Examples (DO NOT DO THIS)

```bash
# WRONG: Showing IDE prompt AND sending notify.sh simultaneously
# WRONG: Using notify.sh in IDE mode for approvals
# WRONG: Using heredoc/multiline echo to pipe into notify.sh (triggers permission prompts)
# WRONG: Asking "Want to switch to phone mode?" when user already said "use iMessage"
# WRONG: Using Task sub-agents to run send.sh/notify.sh (permissions fail in sub-agents)
```

## Requirements

- macOS with Messages app signed into iMessage
- Full Disk Access granted to the terminal app (for reading chat.db)
- An existing iMessage conversation with the recipient
- **Commands whitelisted** to avoid IDE approval prompts (see below)

## Whitelist Commands

**Problem:** Claude Code's CLI gates every Bash command through a permission check. If the command pattern isn't whitelisted, the IDE shows "Do you want to proceed?" — blocking phone mode since the user is away.

**Solution:** Run the whitelist script from inside each repo where you want phone mode:

```bash
cd /path/to/your/repo
~/.claude/skills/imessage-notify/whitelist_commands.sh
```

This injects permission entries into:
1. The repo's `.claude/settings.local.json`
2. The global `~/.claude/settings.json`

Run once per repo. It's idempotent (safe to run multiple times).

**The `-f` flag solves the multiline gap.** The whitelisted pattern `notify.sh *` matches `notify.sh -f /tmp/file.txt 600 10` because it's a single line. Without `-f`, multiline piped commands (`echo "...\n..." | notify.sh -`) would NOT match the glob because `*` doesn't cross newlines.

## Error Handling

All scripts include error checking and will:
- Check if Messages app is running before attempting to send
- Validate AppleScript execution succeeded
- Provide specific troubleshooting steps on failure
- Return non-zero exit codes on errors

## Reply Routing / Aliases

When you send a message to `nnosse@wgu.edu`, your phone might reply from a
different iMessage identity (e.g., `+13522339160`). macOS puts that reply in a
separate chat, so `read.sh` won't find it unless it knows about all your identities.

**How it works:** `read.sh` has a `RECIPIENT_ALIASES` variable. The SQL query uses
`WHERE chat_identifier IN (recipient, alias1, alias2, ...)` to check all chat
windows for replies.

**Configure aliases during install:**
```bash
./install.sh
# The installer will prompt for aliases after the phone/email step.
# It will attempt auto-detection from chat.db (Ventura+) first.
```

**Configure aliases manually (non-interactive):**
```bash
./install.sh --phone nnosse@wgu.edu --aliases "+13522339160 noelnosse@gmail.com"
```

**Reconfigure aliases post-install:**
```bash
~/.claude/skills/imessage-notify/whitelist_commands.sh nnosse@wgu.edu --aliases "+13522339160 noelnosse@gmail.com"
```

**Find your iMessage identities:**
Open Messages.app → Settings → iMessage. The "You can be reached for messages at"
list shows all your addresses. Add any that your phone might use as the sender.

## Troubleshooting

### "ERROR: Messages app is not running"
- Open `/System/Applications/Messages.app`
- Sign in to iMessage (Messages > Settings > iMessage)
- Verify your Apple ID is active

### "ERROR: Failed to send iMessage via AppleScript"
1. Check Messages is signed in: Messages > Settings > iMessage
2. Verify you have an existing conversation with the recipient
3. Try sending a manual test message in Messages app first
4. Check Full Disk Access: `~/.claude/skills/imessage-notify/check_fda.sh`

### "TIMEOUT: No reply received"
- Your phone may reply from a different iMessage address — configure aliases (see "Reply Routing / Aliases" above)
- Verify you replied to the correct iMessage conversation
- Check that your phone has connectivity
- Ensure the RECIPIENT in send.sh and read.sh match
- Look for the request ID in the message tag: `[repo-name|REQ-abc123]`

### Messages send but are not received
- Verify RECIPIENT is set correctly in both `send.sh` and `read.sh`
- Check for special characters in messages (now properly escaped)
- Verify Messages app can send to the recipient normally
- Check iMessage service status at https://www.apple.com/support/systemstatus/

### IDE still shows "Do you want to proceed?"
- Run `~/.claude/skills/imessage-notify/whitelist_commands.sh` from the repo
- Make sure you're using `-f` file mode for multiline messages, not heredoc/pipe
- Click "Yes" once as fallback — the approval is remembered for that session

## FDA Verification

The scripts automatically check for Full Disk Access before reading `chat.db`. If FDA is missing, they will detect your terminal app (PyCharm, VS Code, iTerm, Terminal, Cursor, Warp) and print specific setup instructions. You can also run the check manually:

```bash
~/.claude/skills/imessage-notify/check_fda.sh
```