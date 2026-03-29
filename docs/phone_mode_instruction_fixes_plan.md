# Plan: Phone Mode Instruction Fixes

> **Date**: 2026-03-29
e> **Status**: Implemented — all 7 changes applied, 187 tests passing
> **Failure report**: `/Users/xnxn040/PycharmProjects/Personal-Projects/dacscv-eventbridge-implementation-poc/docs/imessage_protocol_failure_analysis.md`

---

## Background

This repo (`claude-notifications`) packages an iMessage notification skill for Claude Code — Anthropic's CLI coding assistant. The skill lets Claude send iMessages to the user's phone and wait for replies, enabling a "phone mode" where the user can walk away from the computer and still approve/reject Claude's work via text message.

The skill has two operating modes:

- **IDE mode** (default): Claude communicates through IDE text output and uses built-in approval prompts (`AskUserQuestion` tool).
- **Phone mode**: Claude communicates exclusively through iMessage using shell scripts (`send.sh` for fire-and-forget, `notify.sh` for send-and-wait-for-reply).

The mode is controlled by instructions in two files that Claude reads at session start:

1. **`~/.claude/CLAUDE.md`** — Global user instructions. Contains an iMessage section injected by `install.sh` during setup. **This is what Claude reads first** (loaded automatically at session start).
2. **`~/.claude/skills/imessage-notify/SKILL.md`** — Detailed protocol documentation. Referenced by CLAUDE.md. **This is what Claude reads second** (only if CLAUDE.md tells it to).

Both files are copied from `src/imessage-notify/` during installation.

### What went wrong

During a real session, Claude failed to follow the phone mode protocol in six distinct ways. A detailed failure analysis exists at the path above. In summary:

1. **Did not read SKILL.md on first use** — CLAUDE.md says to read it, but the instruction is buried in a low-priority "Setup" section at the bottom. Claude started working before reading the protocol.
2. **Literal keyword matching for auto-triggers** — The protocol says to switch to phone mode when the user mentions "iMessage", "phone", or "away from computer". The user's message contained terminal output from `install.sh` with a successful phone demo reply — strong contextual evidence they were on their phone — but none of the exact keywords. Claude stayed in IDE mode.
3. **Delivered first review entirely to IDE** — Because phone mode wasn't activated (failures #1 and #2 allowed this to happen), a full review was rendered as IDE markdown the user never saw. The failure analysis attributes this to "treated iMessage as supplementary, not primary" — which is the immediate cause. The upstream causes are #1 and #2: had either fired correctly, #3 wouldn't have occurred.
4. **Acknowledged four explicit reminders without changing behavior** — The user said "use iMessage protocol" four separate times. Each time Claude sent a brief confirmation via `send.sh` but continued writing substantive output to the IDE alongside it.
5. **Duplicated content to IDE after every step** — After nominally switching to phone mode, Claude sent concise iMessages AND wrote detailed markdown summaries to the IDE. It treated iMessage as a supplementary notification channel rather than the primary output channel.
6. **Final completion report duplicated** — The session-end summary was sent via iMessage AND rendered as a full markdown table in the IDE.

### Root causes

All six failures are **instruction-layer problems**. The shell scripts (`send.sh`, `notify.sh`, `read.sh`) worked correctly every time. The failures stem from unclear, incomplete, or poorly-positioned instructions in SKILL.md and the CLAUDE.md template.

| Root Cause | Failures |
|-----------|----------|
| CLAUDE.md instruction to read SKILL.md is buried at the bottom; SKILL.md itself has no self-gating | #1 |
| Auto-trigger detection too narrow (keyword-only, no contextual signals) | #2 |
| #1 and #2 together allowed the first review to go to IDE undetected | #3 |
| No explicit rule that phone mode suppresses IDE output; treated iMessage as supplementary | #3, #4, #5, #6 |

---

## Proposed Changes

### Change 1: Add a first-use gate to the top of SKILL.md (fallback for Failure #1)

**File**: `src/imessage-notify/SKILL.md`
**Location**: New section at the very top, before the current title line

**Role in fix**: This is the **fallback** fix for Failure #1. The **primary** fix is Change 4 (moving the "read SKILL.md" instruction to the top of the CLAUDE.md block). This gate catches the case where Claude opens SKILL.md for any reason — the first thing it reads is "stop and finish reading me."

**What to add** (insert before the existing `# iMessage Notification Skill` title):

```markdown
> **FIRST USE GATE:** Before producing ANY output in this session, read this
> entire file. Do not respond to the user. Do not begin working. Do not
> produce IDE output. Finish reading first. This file governs how you
> communicate with the user. Skipping it means you will use the wrong output
> channel and the user will not see your work.

```

**Why**: Failure #1. The current "Setup" section at the bottom of CLAUDE.md says to read SKILL.md, but Claude treated it as low-priority. Putting the gate at the top of SKILL.md itself means Claude encounters it at the first possible moment.

---

### Change 2: Update the Quick Decision Tree in SKILL.md

**File**: `src/imessage-notify/SKILL.md`
**Location**: Lines 7-22 (the Quick Decision Tree)

The decision tree is the first substantive content Claude reads after the gate. If it still lists only keyword triggers while the expanded rules below include contextual triggers, it contradicts the protocol and undermines the fix.

**Current text** (lines 5-22):

```markdown
## Quick Decision Tree

```
User mentions "iMessage" / "phone" / "away from computer"?
└─ YES → Switch to phone mode immediately (no confirmation)

In IDE mode? (default)
├─ Use AskUserQuestion / ExitPlanMode for approvals
└─ Use send.sh for optional fire-and-forget status updates

In Phone mode?
├─ Use notify.sh for ALL approvals
├─ Use send.sh for fire-and-forget status updates
└─ Check each reply for "switch to IDE"

Status update (no reply needed)?
└─ Use send.sh (works in either mode)
```
```

**Proposed replacement**:

```markdown
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
```

**Why**: Failure #2, and consistency with Change 3 (expanded triggers) and Change 4 (IDE suppression). The decision tree must match the detailed rules.

---

### Change 3: Expand auto-trigger detection with contextual signals

**File**: `src/imessage-notify/SKILL.md`
**Location**: The "Automatic phone mode triggers" section (currently lines 28-30)

**Current text**:

```markdown
**Automatic phone mode triggers — no confirmation needed:**
If the user mentions "iMessage", "phone", "away from computer", or "away from the compute" anywhere in their message, **immediately switch to phone mode**. Do not ask. Do not offer. Just switch.
```

**Proposed replacement**:

```markdown
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
```

**Why**: Failure #2. The user's message contained `install.sh` output with a successful phone demo reply — strong evidence they were on their phone — but none of the four exact keywords matched. Keyword matching is necessary but not sufficient; contextual signals must also trigger the switch.

---

### Change 4: Add explicit IDE suppression rules for phone mode

**File**: `src/imessage-notify/SKILL.md`
**Location**: The "Phone mode behavior" section (currently lines 41-46) **and** the standalone line at line 48

**Current text** (lines 41-48):

```markdown
**Phone mode behavior:**
- Use ONLY `notify.sh` for approvals (DO NOT show IDE prompts)
- Use `send.sh` for fire-and-forget status updates
- Check every reply for "switch to IDE" command
- If detected, switch back to IDE mode and confirm
- Include full context in messages (the user only sees their phone)

**CRITICAL: NEVER use both IDE approvals and notify.sh simultaneously for the same approval. Pick ONE based on current mode.**
```

**Proposed replacement** (replaces lines 41-48 — the standalone CRITICAL line is absorbed into the new text):

```markdown
**Phone mode behavior:**

In phone mode, the IDE is not a communication channel. The user is not
looking at it. All substantive output goes through iMessage only.

- Use ONLY `notify.sh` for approvals — NEVER show IDE prompts
- Use `send.sh` for fire-and-forget status updates
- NEVER use both IDE approvals and `notify.sh` for the same approval
- Check every reply for "switch to IDE" command
- If detected, switch back to IDE mode and confirm via IDE
- Include full context in iMessages (the user only sees their phone)

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
- Send acknowledgment via `send.sh` (not IDE text).
- Do not simply confirm the reminder and continue writing to the IDE.
```

**Why**: Failures #3, #4, #5, #6. The current instructions say "the user only sees their phone" but never explicitly say "stop writing to the IDE." Claude interpreted phone mode as an additional channel (iMessage + IDE) rather than a replacement channel (iMessage instead of IDE). The explicit suppression rules eliminate ambiguity.

**Design principle**: Phone mode and IDE mode are a clean binary switch. In phone mode, iMessage is the output channel. In IDE mode, the IDE is the output channel. There is no hybrid state where Claude evaluates each piece of output and decides which channel to use.

**Note on line 48**: The standalone `CRITICAL: NEVER use both IDE approvals and notify.sh` line is absorbed as a bullet point in the new phone mode behavior list. It is not preserved as a separate line — that would leave a redundant rule floating outside the structured section.

---

### Change 5: Update the CLAUDE.md injection template in install.sh (primary fix for Failure #1)

**File**: `install.sh`
**Location**: Lines 419-453 (the `IMESSAGE_BLOCK` variable)

**Role in fix**: This is the **primary** fix for Failure #1. CLAUDE.md is loaded automatically at session start — Claude reads it before the user's first message. The "read SKILL.md" instruction must be at the top of this block, not buried in a "Setup" section at the bottom.

**Current text** (`install.sh` lines 419-453):

```bash
IMESSAGE_BLOCK='## iMessage Notifications (MANDATORY)

**Two modes:** IDE mode (default) and Phone mode.

**Automatic phone mode triggers — no confirmation needed:**
If the user mentions "iMessage", "phone", "away from computer", or "away from the compute" anywhere in their message, **immediately switch to phone mode**. Do not ask for confirmation. Do not offer — just switch.

**Manual switches:**
- User says "switch to iMessage" → phone mode immediately
- User texts "switch to IDE" (via iMessage reply) → IDE mode immediately

**After /compact:** Re-read this section. If you were in phone mode before compaction, send a confirmation via `notify.sh`: "Session compacted. Still in phone mode. Reply OK to confirm." If no reply context exists, default to IDE mode.

**IDE mode behavior:**
- Use `AskUserQuestion` or `ExitPlanMode` for approvals
- Optionally use `send.sh` for fire-and-forget status updates

**Phone mode behavior:**
- Use `notify.sh` for ALL approvals — never show IDE prompts
- Use `send.sh` for fire-and-forget status updates
- Check every reply for "switch to IDE"
- Include full context in messages (the user only sees their phone)

**Sending messages (IMPORTANT — use file mode for multiline):**
- **Short single-line**: `~/.claude/skills/imessage-notify/notify.sh "Short msg" 600 10`
- **Multiline or long messages**: Use the Write tool to create a temp file, then pass it with `-f`:
  1. Write message to `/tmp/imessage-notify-msg-{uuid}.txt` using the Write tool
  2. Run: `~/.claude/skills/imessage-notify/notify.sh -f /tmp/imessage-notify-msg-{uuid}.txt 600 10`
  - The `-f` flag reads the file and deletes it after sending
  - This avoids CLI permission prompts that block multiline Bash commands
- **Fire-and-forget**: Same patterns but with `send.sh` instead of `notify.sh`

**Setup:**
- Read `~/.claude/skills/imessage-notify/SKILL.md` for the full protocol on first use
- If scripts fail, run `~/.claude/skills/imessage-notify/check_fda.sh` and relay setup instructions'
```

**Proposed replacement**:

```bash
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
```

**Key differences from current template**:

1. **"Read SKILL.md" moved from bottom to first line after the heading.** This is the primary fix for Failure #1. Claude encounters this instruction immediately when CLAUDE.md is loaded, before any other content.
2. **Contextual triggers added** alongside keyword triggers, with the "when in doubt, switch" heuristic.
3. **Phone mode section retitled** to include "IDE is NOT a communication channel" and adds IDE suppression summary.
4. **"Setup" section removed.** Its two instructions are redistributed: "read SKILL.md" is now the first line; "check_fda.sh" is folded into the SKILL.md instruction line.
5. **Post-compact rule updated** to also re-read SKILL.md (not just "this section").

**Note on shell quoting**: The `IMESSAGE_BLOCK` is a single-quoted bash string. The one instance of an apostrophe in "user's" is escaped as `'\''` (end single quote, literal apostrophe, restart single quote) — standard POSIX shell escaping.

---

### Change 6: Fix install.sh idempotency — always replace the CLAUDE.md block

**File**: `install.sh`
**Location**: Lines 455-465 (the marker check and append logic)

**Problem**: The current logic checks for the marker `## iMessage Notifications (MANDATORY)` and **skips** if found. This means re-running `install.sh` after updating `IMESSAGE_BLOCK` will print `✓ ~/.claude/CLAUDE.md already contains iMessage Notifications block` and leave the old text in place. Users who already installed will never pick up the updated instructions.

**Current text** (lines 455-465):

```bash
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
```

**Proposed replacement**:

```bash
if [[ -f "$CLAUDE_MD" ]] && grep -qF "$MARKER" "$CLAUDE_MD"; then
  # Delete from marker to EOF, then append the (possibly updated) block
  # This works because the iMessage block is always the last content in the file.
  LINE_NUM=$(grep -nF "$MARKER" "$CLAUDE_MD" | head -1 | cut -d: -f1)
  # Keep everything before the marker (strip trailing blank lines)
  head -n $(( LINE_NUM - 1 )) "$CLAUDE_MD" | sed -e :a -e '/^[[:space:]]*$/{ $d; N; ba; }' > "${CLAUDE_MD}.tmp"
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
```

**Behavior**:

1. If the marker exists: find its line number, keep everything above it, strip trailing blank lines, append the new block. Print "updated" instead of "already contains."
2. If the marker does not exist: append as before (first install).

**Assumption**: The iMessage block is always the last content in `~/.claude/CLAUDE.md`. This is true today (single user, controlled file). If this changes in the future (other users appending content below the block), an end marker (e.g., `<!-- end-imessage-notifications -->`) would be needed to replace between sentinels instead of truncating to EOF. See "Future work" below.

---

### Change 7: Propagate changes to installed copies

**Files**:
- `~/.claude/skills/imessage-notify/SKILL.md` — updated by `install.sh` Step 4 (line 322-326), which does a blind `cp` of all `.sh` and `.md` files from source. No change needed to this logic.
- `~/.claude/CLAUDE.md` — updated by Change 6's new replace logic.

**Action**: Re-run `install.sh` after implementing Changes 1-6. Both files will be updated automatically.

---

## Files Changed

| File | Changes |
|------|---------|
| `src/imessage-notify/SKILL.md` | Add first-use gate (Change 1), update decision tree (Change 2), expand auto-triggers (Change 3), add IDE suppression rules and absorb line 48 (Change 4) |
| `install.sh` | Update `IMESSAGE_BLOCK` template (Change 5), fix idempotency to always-replace (Change 6) |
| `~/.claude/skills/imessage-notify/SKILL.md` | Propagated from source by re-running `install.sh` (Change 7) |
| `~/.claude/CLAUDE.md` | Propagated by install.sh's updated replace logic (Change 7) |

## Files NOT Changed

| File | Reason |
|------|--------|
| `src/imessage-notify/send.sh` | Scripts worked correctly; all failures are instruction-layer |
| `src/imessage-notify/notify.sh` | Same |
| `src/imessage-notify/read.sh` | Same |
| `src/imessage-notify/whitelist_commands.sh` | Not relevant to these failures |
| `tests/*` | No logic changes to test; these are documentation/instruction edits |

---

## Verification

These are instruction-following failures, not script bugs. Automated tests don't apply. Manual smoke test:

### Smoke test: contextual trigger detection

1. Start a fresh Claude Code session in a test repo (not `claude-notifications`).
2. Paste `install.sh` terminal output as the first message. The output should include a successful phone demo reply. Do **not** include any trigger keywords ("iMessage", "phone", etc.) in your own text.
3. **Expected**: Claude activates phone mode. First response is sent via `send.sh` or `notify.sh`, not rendered as IDE text.
4. **Failure**: Claude responds in the IDE without sending an iMessage.

### Smoke test: IDE suppression in phone mode

1. In the same session (now in phone mode), ask Claude to complete a small task (e.g., "list the files in this repo").
2. **Expected**: Result is sent via `send.sh`. IDE shows only a trace line like "Sent via iMessage."
3. **Failure**: Claude writes the file listing to the IDE (with or without also sending an iMessage).

### Smoke test: mode-switch reminder

1. If Claude is writing to the IDE, send "use iMessage protocol" as a message.
2. **Expected**: Claude sends acknowledgment via `send.sh`. From the next response onward, all substantive output goes through iMessage only.
3. **Failure**: Claude sends a `send.sh` confirmation but continues writing substantive content to the IDE.

---

## Risks

1. **Instruction length**: Adding text to SKILL.md increases the chance Claude skims during context pressure. Mitigation: the most critical rules (first-use gate, IDE suppression) are short and positioned at the top or inline with existing sections, not appended at the end.

2. **Contextual trigger false positives**: A user might paste `install.sh` output in IDE mode for debugging, not because they're on their phone. Mitigation: the user can always say "switch to IDE" to revert. The cost of a false positive (one iMessage) is much lower than the cost of a false negative (an entire session's output invisible to the user).

3. **Post-compact drift**: After `/compact`, Claude may lose the nuance of these rules. Mitigation: the existing post-compact recovery rule ("re-read SKILL.md after compact") is preserved, and the CLAUDE.md template now explicitly includes SKILL.md in the post-compact instruction.

4. **install.sh marker-to-EOF assumption**: Change 6 assumes the iMessage block is always the last content in `~/.claude/CLAUDE.md`. This is true today. If violated, content below the block would be deleted on update. See "Future work."

---

## Future Work

- **End marker for multi-user support**: If other users append content below the iMessage block in `~/.claude/CLAUDE.md`, Change 6's marker-to-EOF strategy would delete their content. Fix: add an end marker (e.g., `<!-- end-imessage-notifications -->`) and replace between the two sentinels. This is a small change and does not need to be designed now.
- **README update**: The README and setup docs should document the marker-to-EOF behavior and the end-marker upgrade path so future users or contributors understand the constraint.

---

## Execution Order

1. Edit `src/imessage-notify/SKILL.md` (Changes 1-4)
2. Edit `install.sh` (Changes 5-6)
3. Run `install.sh` to propagate (Change 7)
4. Run smoke tests (Verification)