# iMessage Notification Demo Script

This script demonstrates the dynamic mode-switching functionality between IDE and phone approvals in Claude Code.

## Prerequisites

Before running this demo, ensure:
- iMessage skill installed via `./install.sh`
- Full Disk Access granted to your terminal app
- Messages app running and signed into iMessage
- CLAUDE.md includes iMessage notification instructions

**Quick verification:**
```bash
~/.claude/skills/imessage-notify/send.sh "Setup verified - ready for demo"
```
You should receive that message on your phone within seconds.

## Demo Overview

This demo will show:
1. **IDE mode** (default) - Approvals in the IDE
2. **Mode switching** - Offering phone mode for multi-step tasks
3. **Phone mode** - Approvals via iMessage only
4. **Switch back** - Returning to IDE mode from phone

---

## How to Run the Demo

### Step 1: Start a New Claude Code Session

Open any repository and start Claude Code.

### Step 2: Copy and Paste This Prompt

```
Test the iMessage notification system with me using a 5-step simulated workflow:

STEP 1: Start in IDE mode (default) and ask me a simple approval question

STEP 2: I'll say "switch to iMessage" — switch to phone mode immediately (no confirmation needed)

STEP 3: In phone mode, send the next 3 approvals via iMessage ONLY using notify.sh (NO IDE prompts during phone mode). Permission prompts for Write/Edit should route through iMessage automatically via the hook.

STEP 4: Watch for "switch to IDE" in my phone replies. When detected, switch back to IDE mode

STEP 5: Complete the remaining approvals in IDE mode using AskUserQuestion

Follow the protocol in ~/.claude/skills/imessage-notify/SKILL.md strictly:
- In IDE mode: Use AskUserQuestion or ExitPlanMode (NOT notify.sh)
- In phone mode: Use ONLY notify.sh (NO IDE prompts)
- NEVER show both IDE and phone prompts for the same approval

Begin the 5-step demo workflow now.
```

### Step 3: Follow the Workflow

#### Expected Flow:

**1. IDE Approval (Step 1)**
- Claude shows an approval prompt in the IDE
- Respond in the IDE (click an option)

**2. Mode Switch**
- Say: **"switch to iMessage"**
- Claude switches to phone mode immediately (no confirmation prompt)

**3. Phone Approvals (Steps 2-4)**
- Check your phone - you should see iMessages like:
  ```
  [your-repo|REQ-abc123] STEP 2/5: [description]. Reply APPROVE to proceed, or 'switch to IDE' to return to IDE mode.
  ```
- Reply from your phone: **"APPROVE"** (or just "approve")
- Repeat for steps 3 and 4
- **IMPORTANT:** During phone mode, NO IDE prompts should appear

**4. Switch Back to IDE**
- On step 3 or 4, reply from your phone: **"switch to IDE"**
- Claude should detect this and confirm switching back

**5. IDE Approval (Final Step)**
- Claude shows remaining approvals in the IDE
- Respond in the IDE

---

## What You Should See

### Correct Behavior

1. **IDE mode**: Approvals show in IDE, no phone messages
2. **Phone mode activation**: Claude creates flag file, asks "What would you like me to work on?" via iMessage and waits for your reply
3. **Phone mode**: All communication on phone, NO IDE interruptions
4. **Permission routing**: Write/Edit/Read prompts arrive on phone as "Allow? YES or NO" (not in IDE)
5. **Continuous loop**: After each task, Claude asks "What's next?" via iMessage — never stops and waits for IDE input
6. **No double-approval**: You only respond once per step (either phone OR IDE)
7. **Immediate delivery**: Phone messages arrive within 1-2 seconds

### Incorrect Behavior (Report if you see this)

1. **Claude stops after switching**: Claude sends a fire-and-forget message and goes idle — should use notify.sh to wait for your task
2. **IDE prompts in phone mode**: "Do you want to proceed?" appears in IDE — permission hook should route it to phone
3. **No flag file**: `ls /tmp/imessage-notify-phone-mode` shows nothing after switching — Claude forgot the activation sequence
4. **Double prompts**: Both IDE and phone ask for approval simultaneously
5. **No messages**: Phone messages never arrive (check troubleshooting)
6. **Mode stuck**: Can't switch between modes

---

## Troubleshooting

### Messages not arriving on phone

```bash
# Test send directly
~/.claude/skills/imessage-notify/send.sh "Direct test message"
```

If this fails, check:
1. Messages app is running and signed into iMessage
2. RECIPIENT is set correctly in both `send.sh` and `read.sh`
3. You have an existing conversation with yourself
4. Full Disk Access is granted: `~/.claude/skills/imessage-notify/check_fda.sh`

### "ERROR: Messages app is not running"

```bash
# Open Messages app
open /System/Applications/Messages.app
```

Verify you're signed into iMessage (Messages > Settings > iMessage)

---

## Advanced Demo Scenarios

### Scenario 1: IDE-Only Workflow (Single Approval)

**Prompt:**
```
I need approval to delete a test file. Ask me for approval in the IDE.
```

**Expected:** Single IDE approval, no phone mode offered (not multi-step)

### Scenario 2: Manual Mode Switch

**Prompt:**
```
Ask me 3 approval questions. Start in IDE mode.
```

After the first approval, respond: **"switch to iMessage"**

**Expected:** Claude switches to phone mode for remaining approvals

### Scenario 3: Fire-and-Forget Notifications

**Prompt:**
```
Run a simulated long task (10 seconds) and notify me on my phone when complete. Don't wait for a reply.
```

**Expected:**
- Claude runs `sleep 10`
- Uses `send.sh` to notify (not `notify.sh`)
- Continues without waiting for reply

---

## Demo Checklist

Use this to verify all features work:

- [ ] IDE mode: Single approval in IDE (no phone)
- [ ] Keyword trigger: Switches to phone mode on "switch to iMessage"
- [ ] Flag file created: `ls /tmp/imessage-notify-phone-mode` exists after switch
- [ ] First contact: Claude asks "What would you like me to work on?" via notify.sh (waits for reply)
- [ ] Phone approvals: Messages arrive immediately
- [ ] Permission routing: Write/Edit prompts go to phone, not IDE
- [ ] No IDE interrupts: IDE only shows brief trace lines during phone mode
- [ ] Continuous loop: After task, Claude asks "What's next?" (doesn't stop)
- [ ] Switch to IDE: Detects "switch to IDE" from phone, removes flag file
- [ ] Error handling: Shows helpful messages on failure
- [ ] Fire-and-forget: `send.sh` works for status updates
- [ ] Multi-repo: Works correctly with multiple Claude sessions