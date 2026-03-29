# Plan: PermissionRequest Hook for iMessage Approval Routing

## Goal

Route Claude Code's IDE permission prompts (Write, Edit, etc.) through iMessage when phone mode is active, instead of showing them in the IDE where the user isn't looking.

## Architecture

```
Claude tool call → PermissionRequest hook fires → permission_gate.sh
  ├── Phone mode OFF → exit 0 (fall through to normal IDE prompt)
  └── Phone mode ON  → format message → notify.sh → wait for reply
                        ├── Reply YES → JSON {"behavior":"allow"} → tool executes
                        ├── Reply NO  → JSON {"behavior":"deny"} → tool blocked
                        └── Timeout   → exit 2 + stderr feedback → tool blocked
```

## Completed Work (all in working tree)

- [x] `Bash(*)` added to whitelist_commands.sh, conftest.py, uninstall.sh
- [x] `docs/phone_mode_instruction_fixes_plan.md` deleted via git rm
- [x] `src/imessage-notify/permission_gate.sh` — created (hook script)
- [x] `tests/test_permission_gate.py` — created (26 tests, all passing)
- [x] `tests/conftest.py` — added permission_gate_sandbox fixture + mock notify.sh + run_permission_gate helper
- [x] `src/imessage-notify/whitelist_commands.sh` — added inject_hooks() for PermissionRequest + SessionEnd + SessionStart hooks
- [x] `uninstall.sh` — added hook removal (step 2b) + phone mode flag cleanup (step 5)
- [x] All 213 tests pass, ruff clean

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `src/imessage-notify/permission_gate.sh` | CREATE | Hook script — routes permission requests through iMessage |
| `tests/test_permission_gate.py` | CREATE | TDD tests for hook script |
| `src/imessage-notify/whitelist_commands.sh` | MODIFY | Inject hook config into settings.json |
| `uninstall.sh` | MODIFY | Remove hook config during uninstall |
| `tests/conftest.py` | MODIFY | Add hook-related fixtures/helpers |

## Detail: permission_gate.sh

### Input (stdin JSON from Claude Code)

```json
{
  "session_id": "abc123",
  "hook_event_name": "PermissionRequest",
  "tool_name": "Write",
  "tool_input": {"file_path": "/foo/bar.py", "content": "..."},
  "cwd": "/path/to/project"
}
```

### Phone mode flag (production-ready)

- File: `/tmp/imessage-notify-phone-mode`
- Created by Claude via `touch /tmp/imessage-notify-phone-mode` when entering phone mode
- Deleted by Claude via `rm -f /tmp/imessage-notify-phone-mode` when switching to IDE
- If flag absent → exit 0 (normal IDE prompt shows)
- If flag present AND not stale → route through iMessage

**Stale flag prevention (3 layers):**

1. **TTL-based expiry**: permission_gate.sh checks flag file modification time. Flags older than 4 hours are treated as stale — auto-deleted and ignored. This catches crashes where no cleanup hook ran.
2. **SessionEnd hook**: Automatically deletes the flag when a Claude Code session ends normally (exit, clear, resume, logout).
3. **SessionStart hook**: Deletes any leftover flag when a new session starts. Catches flags from sessions that crashed hard (SIGKILL) before SessionEnd could fire.

**Multi-session limitation**: Only one session can be in phone mode at a time (single global flag file). This is acceptable since phone mode implies "user is on their phone" which is a user-level state, not per-session.

### Message formatting by tool type

```
Bash:    "Run command: git push origin main"
Write:   "Write file: /foo/bar.py (245 chars)"
Edit:    "Edit file: /foo/bar.py"
Read:    "Read file: /foo/bar.py"
Other:   "Use tool: ToolName"
```

Full message sent via notify.sh:
```
[Permission] Claude wants to:
Write file: src/main.py (1523 chars)
Allow? Reply YES or NO.
```

### Reply parsing

- Reply contains "yes" (case-insensitive) → allow
- Reply contains "no" (case-insensitive) → deny
- Anything else → deny (safe default) with feedback "Unclear reply: '<reply>'. Treated as NO."

### Timeout behavior

- notify.sh timeout: 300s (default)
- Hook timeout: 600s (allows buffer beyond notify.sh timeout)
- If notify.sh times out (no reply) → exit 2 + stderr "No reply received within timeout. Permission denied."

### Exit behavior

| Condition | Exit code | Stdout | Stderr |
|-----------|-----------|--------|--------|
| Phone mode OFF | 0 | (empty) | (empty) |
| Reply YES | 0 | `{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}` | (empty) |
| Reply NO | 0 | `{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"deny"}}}` | (empty) |
| Timeout | 2 | (empty) | "No reply received. Permission denied." |
| notify.sh fails | 0 | (empty) | (empty) — fall through to IDE prompt |

Note: If notify.sh itself fails (scripts not configured, Messages not running), we fall through to the IDE prompt rather than blocking. This is a graceful degradation path.

### Interaction with Bash(*)

`Bash(*)` auto-approves all Bash commands, so the PermissionRequest hook never fires for Bash tools. This means:
- Bash commands: auto-approved (no iMessage, no IDE prompt)
- Write/Edit/Read/other tools: routed through iMessage when phone mode is on

This is the intended behavior. Bash(*) reduces iMessage noise. If the user later decides they want Bash commands routed through iMessage too, remove `Bash(*)` from the permissions.

## Detail: Hook configuration (injected by whitelist_commands.sh)

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/skills/imessage-notify/permission_gate.sh",
            "timeout": 600
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "rm -f /tmp/imessage-notify-phone-mode",
            "timeout": 5
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "rm -f /tmp/imessage-notify-phone-mode",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

Injected into: `~/.claude/settings.json` only (global — hook is system-wide).
NOT injected into per-repo settings (hook behavior is the same across repos).

## Detail: whitelist_commands.sh changes

Add a new helper `inject_hooks()` that:
1. Reads existing settings.json
2. Merges the hook config (idempotent — don't duplicate)
3. Writes back

Called after `inject_permissions()` in the main flow.

## Detail: uninstall.sh changes

Add a step that removes the `PermissionRequest` hook entry from `~/.claude/settings.json`. Also removes the phone mode flag file.

## Test Plan (TDD)

### test_permission_gate.py

1. **test_no_phone_mode_flag** — No flag file → exit 0, empty stdout (fall through to IDE)
2. **test_phone_mode_yes_reply** — Flag exists, mock notify.sh returns "yes" → JSON allow output
3. **test_phone_mode_no_reply** — Flag exists, mock notify.sh returns "no" → JSON deny output
4. **test_phone_mode_timeout** — Flag exists, mock notify.sh exits 1 (timeout) → exit 2
5. **test_format_bash_tool** — Correct message format for Bash tool input
6. **test_format_write_tool** — Correct message format for Write tool input
7. **test_format_edit_tool** — Correct message format for Edit tool input
8. **test_format_unknown_tool** — Correct message format for unknown tool
9. **test_case_insensitive_yes** — "YES", "Yes", "y" all treated as allow
10. **test_ambiguous_reply** — "maybe" treated as deny with feedback
11. **test_notify_failure_fallthrough** — notify.sh fails → exit 0 (fall through to IDE)
12. **test_stdin_parsing** — Correctly parses JSON from stdin
13. **test_stale_flag_expired** — Flag file older than 4 hours → exit 0, flag deleted (treated as no phone mode)
14. **test_fresh_flag_not_expired** — Flag file created recently → routes through iMessage normally

### conftest.py additions

- `permission_gate_sandbox` fixture: copies permission_gate.sh, creates mock notify.sh, provides flag file path
- `run_permission_gate()` helper: runs the script with given stdin JSON and env

### test_whitelist_commands.py (existing tests should still pass)

- May need new test for hook injection into settings

### test_uninstall.py (existing tests should still pass)

- May need new test for hook removal from settings

## Verification

1. `uv run pytest -m "not integration"` — all tests pass
2. `uvx ruff check` — no lint errors
3. Manual test: activate phone mode flag, trigger a Write permission, verify iMessage arrives
