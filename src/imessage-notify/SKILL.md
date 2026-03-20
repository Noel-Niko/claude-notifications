# iMessage Notification Skill

Send iMessages to the user's phone and read their replies. Use this for approvals and notifications with dynamic mode-switching between IDE and phone.

## Quick Decision Tree

```
Need user approval?
├─ In IDE mode? (default)
│  ├─ Single approval → Use AskUserQuestion (NOT notify.sh)
│  └─ 3+ step task → Offer phone mode switch via AskUserQuestion
│     ├─ User says YES → Switch to phone mode
│     └─ User says NO → Stay in IDE mode
│
└─ In Phone mode?
   └─ Use notify.sh for ALL approvals
      └─ Check each reply for "switch to IDE" command

Status update (no reply needed)?
└─ Use send.sh (any mode)
```

## Mode-Switching Protocol (IMPORTANT)

**Two approval modes:**
- **IDE mode** (default): Use IDE tools (`AskUserQuestion`, `ExitPlanMode`) for approvals
- **Phone mode**: Use `notify.sh` for phone-only approvals (user responds via iMessage)

**When to switch modes:**

1. **Start in IDE mode** by default
2. **Offer phone mode** for multi-step tasks (3+ approval points):
   - Use `AskUserQuestion` to ask: "This is a multi-step task. Want to switch to phone approvals? [Yes/No]"
   - If user says yes, switch to phone mode for all subsequent approvals
3. **Manual switch to phone**: User says "switch to iMessage" in any response
4. **Manual switch to IDE**: User texts "switch to IDE" to their phone (while in phone mode)
5. **Track current mode** throughout the session

**In IDE mode:**
- Use `AskUserQuestion` or `ExitPlanMode` for approvals (DO NOT use notify.sh)
- Optionally use `send.sh` for fire-and-forget status updates
- Watch for user saying "switch to iMessage"

**In Phone mode:**
- Use ONLY `notify.sh` for approvals (DO NOT show IDE prompts)
- Check every reply for "switch to IDE" command
- If detected, switch back to IDE mode and confirm

**CRITICAL: NEVER use both IDE approvals and notify.sh simultaneously for the same approval. Pick ONE based on current mode.**

## When to Use

- **Phone mode**: Multi-step tasks where user wants to respond from anywhere
- **Status updates**: Use `send.sh` for fire-and-forget notifications
- **Single approvals**: Default to IDE mode unless user requests phone mode

## Scripts

All scripts are located in `~/.claude/skills/imessage-notify/`.

### Send Only (no wait)

```bash
# Short single-line messages (argument mode):
~/.claude/skills/imessage-notify/send.sh "Your message here"

# Long or multiline messages (stdin mode — avoids permission prompt issues):
echo "Your message here" | ~/.claude/skills/imessage-notify/send.sh -
```

Outputs: `REQ_ID=<id> SENT_EPOCH=<epoch>`

Messages are auto-tagged with the repo name and request ID:
```
[my-repo|REQ-a1b2c3d4] Your message here
```

**IMPORTANT:** For multiline messages, always use stdin mode (`echo "msg" | send.sh -`).
The permission pattern `send.sh *` does not match newlines in arguments, so multiline
argument-mode calls will trigger IDE approval prompts.

### Send and Wait for Reply

```bash
# Short single-line messages:
~/.claude/skills/imessage-notify/notify.sh "Your question here" [timeout_seconds] [poll_interval_seconds]

# Long or multiline messages (stdin mode):
echo "Your question here" | ~/.claude/skills/imessage-notify/notify.sh - [timeout_seconds] [poll_interval_seconds]
```

- Default timeout: 300 seconds (5 minutes)
- Default poll interval: 10 seconds
- Outputs the user's reply text on success, exits 1 on timeout

### Read Only (poll for reply after a known send time)

```bash
~/.claude/skills/imessage-notify/read.sh <sent_epoch> [timeout_seconds] [poll_interval_seconds] [req_id]
```

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

### Example 1: Single approval (IDE mode - default)

```bash
# Use AskUserQuestion tool for single approvals
# DO NOT use notify.sh in IDE mode
```

### Example 2: Multi-step task (offer phone mode)

```bash
# Step 1: Detect multi-step task, offer phone mode switch
# Use AskUserQuestion: "This is a multi-step task. Switch to phone approvals? [Yes/No]"

# Step 2a: If user says YES, switch to phone mode
reply=$(~/.claude/skills/imessage-notify/notify.sh "Step 1/5: Refactor auth module. Reply APPROVE or SKIP." 600 10)
# Continue with notify.sh for all remaining steps
# Check each reply for "switch to IDE" command

# Step 2b: If user says NO, stay in IDE mode
# Use AskUserQuestion for all approvals (DO NOT use notify.sh)
```

### Example 3: Fire-and-forget status update

```bash
# Use send.sh for status updates that don't need a reply
~/.claude/skills/imessage-notify/send.sh "Tests passed. All 42 tests green."
```

### Example 4: Phone mode approval with mode-switch detection

```bash
# When in phone mode, always check replies for "switch to IDE"
reply=$(~/.claude/skills/imessage-notify/notify.sh "Step 2/5: Update database schema. Reply APPROVE or SKIP." 600 10)

if [[ "$reply" =~ [Ss]witch\ to\ IDE ]]; then
    # Switch back to IDE mode, use AskUserQuestion for remaining approvals
    echo "Switching back to IDE mode..."
fi
```

### WRONG Examples (DO NOT DO THIS)

```bash
# WRONG: Showing IDE prompt AND sending notify.sh simultaneously
reply=$(~/.claude/skills/imessage-notify/notify.sh "Approve?" 600 10) &
# AskUserQuestion simultaneously
# This creates double-approval confusion!

# WRONG: Using notify.sh in IDE mode
reply=$(~/.claude/skills/imessage-notify/notify.sh "Single approval question" 600)
# Use AskUserQuestion instead when in IDE mode

# WRONG: Sending iMessage AFTER IDE approval
# AskUserQuestion first
~/.claude/skills/imessage-notify/send.sh "FYI: you already approved this"
# User gets notification AFTER they already responded - useless!
```

## Requirements

- macOS with Messages app signed into iMessage
- Full Disk Access granted to the terminal app (for reading chat.db)
- An existing iMessage conversation with the recipient
- **Commands whitelisted** to avoid IDE approval prompts (see below)

## CRITICAL: Whitelist Commands to Avoid IDE Interruptions

**Problem:** If bash commands require IDE approval, phone mode will be blocked. The IDE will prompt "Do you want to proceed?" BEFORE sending the message to your phone, defeating the purpose of phone mode.

**Solution:** Run the whitelist script from inside each repo where you want phone mode:

```bash
cd /path/to/your/repo
~/.claude/skills/imessage-notify/whitelist_commands.sh
```

This script automatically injects wildcard permission entries into:
1. The repo's `.claude/settings.local.json`
2. The global `~/.claude/settings.json`

Run once per repo. It's idempotent (safe to run multiple times).

**Fallback: Approve when prompted**
- If you still see "Do you want to proceed?" for notify.sh, click "Yes"
- The approval is remembered for future uses in that session

**Alternative: Pre-approve in plan mode**
- Use `ExitPlanMode` with `allowedPrompts` to pre-approve:
  ```
  allowedPrompts: [
    {tool: "Bash", prompt: "iMessage notifications"}
  ]
  ```

## Error Handling

All scripts now include comprehensive error checking and will:
- Check if Messages app is running before attempting to send
- Validate AppleScript execution succeeded
- Provide specific troubleshooting steps on failure
- Return non-zero exit codes on errors

**When errors occur, the scripts will output:**
- Clear error message describing what failed
- Specific troubleshooting steps to fix the issue
- Exit code 1 (check with `$?`)

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
- Verify you replied to the correct iMessage conversation
- Check that your phone has connectivity
- Ensure the RECIPIENT in send.sh and read.sh match
- Look for the request ID in the message tag: `[repo-name|REQ-abc123]`

### Messages send but are not received
- Verify RECIPIENT is set correctly in both `send.sh` and `read.sh`
- Check for special characters in messages (now properly escaped)
- Verify Messages app can send to the recipient normally
- Check iMessage service status at https://www.apple.com/support/systemstatus/

## FDA Verification

The scripts automatically check for Full Disk Access before reading `chat.db`. If FDA is missing, they will detect your terminal app (PyCharm, VS Code, iTerm, Terminal, Cursor, Warp) and print specific setup instructions. You can also run the check manually:

```bash
~/.claude/skills/imessage-notify/check_fda.sh
```