# Uninstall.sh Cleanup Plan

## Goal
Make `uninstall.sh` fully reverse everything `install.sh` creates, so users get a clean slate with no leftover config, permissions, or runtime artifacts.

## Status: IMPLEMENTED ✓

## Completed in this session (prior work)
- [x] `is_from_me` SQL fix in `src/imessage-notify/read.sh` — 8 tests in `TestReadIsFromMeFix`
- [x] Absolute-path permissions in `src/imessage-notify/whitelist_commands.sh` — 5 tests in `TestAbsolutePathPermissions`
- [x] Background execution docs in `src/imessage-notify/SKILL.md`
- [x] Post-compact rule injection in `install.sh` Step 11a — 22 tests in `test_install_claude_md.py`
- [ ] Installed copies at `~/.claude/skills/imessage-notify/` are STALE — need `./install.sh` rerun

## Completed in this session (uninstall.sh)
- [x] Step 1: Absolute-path permissions in PERMISSIONS array — 2 tests
- [x] Step 2: CLAUDE.md block removal (post-compact + iMessage) — 6 tests
- [x] Step 3: Parent .gitignore cleanup — 5 tests
- [x] Step 4: Runtime pending dir cleanup — 2 tests
- [x] Step 5: Local settings note with absolute paths — 2 tests
- [x] Step 6: `--all` flag for auto-clean local settings — 5 tests
- [x] Idempotency — 2 tests
- [x] Output messages — 5 tests
- **Total: 33 new tests in `tests/test_uninstall.py`, 187 total suite (0 failures)**

## Gap Analysis: install.sh creates → uninstall.sh removes

| # | Artifact | Created by | Removed by uninstall.sh? |
|---|----------|------------|--------------------------|
| 1 | `~/.claude/skills/imessage-notify/` (scripts, SKILL.md, .version) | Step 4, 5, 7 | YES — `rm -rf` |
| 2 | Global perms (tilde `~` form) in `~/.claude/settings.json` | Step 6 | YES — python filter |
| 3 | Global perms (absolute `$HOME` form) in `~/.claude/settings.json` | Step 6 (new) | YES — python filter |
| 4 | Per-repo `.claude/settings.local.json` perms (tilde) | Step 6 | Noted (or `--all`) |
| 5 | Per-repo `.claude/settings.local.json` perms (absolute) | Step 6 (new) | Noted (or `--all`) |
| 6 | Post-compact rule in `~/.claude/CLAUDE.md` | Step 11a | YES — regex removal |
| 7 | iMessage Notifications block in `~/.claude/CLAUDE.md` | Step 11b | YES — regex removal |
| 8 | `claude-notifications/` in parent repo's `.gitignore` | Step 1b | YES — line removal |
| 9 | `/tmp/imessage-notify-pending/` (runtime dir) | Runtime by send.sh | YES — `rm -rf` |

## Implementation Plan

### Step 1: Update PERMISSIONS array to include absolute-path forms ✓
- Mirrored the change from `whitelist_commands.sh`: added `$HOME`-expanded variants
- Both tilde and absolute forms removed from `~/.claude/settings.json`

### Step 2: Remove CLAUDE.md blocks ✓
- Removed the iMessage Notifications block (from `## iMessage Notifications (MANDATORY)` to EOF)
- Removed the post-compact rule (line starting with `> **CRITICAL — POST-COMPACT RULE:**`)
- Used python with regex for safe multi-line removal
- CLAUDE.md deleted if empty after removal; left with blocks stripped if other content exists

### Step 3: Clean parent .gitignore ✓
- Detects parent git repo via `cd "$SCRIPT_DIR/.." && git rev-parse --show-toplevel`
- Removes `claude-notifications/` line and its comment `# Claude notifications (cloned installer)`
- Deletes .gitignore if empty after removal

### Step 4: Clean runtime artifacts ✓
- `rm -rf ${PENDING_DIR:-/tmp/imessage-notify-pending}` (testable via env var override)

### Step 5: Update per-repo local settings note ✓
- Both tilde and absolute permission patterns listed in the manual cleanup note
- Suggests `--all` for automatic cleanup

### Step 6: Add --all flag for aggressive cleanup ✓
- Default: clean global settings + installed scripts + CLAUDE.md + .gitignore + runtime artifacts
- `--all`: also auto-clean the parent repo's local `.claude/settings.local.json`

## Test Plan (TDD) ✓
- New file: `tests/test_uninstall.py` — 33 tests
- Fixture: `uninstall_sandbox` in `tests/conftest.py`
- Helper: `run_uninstall()` in `tests/conftest.py`
- Test classes:
  - `TestSkillDirRemoval` (2) — directory removed, idempotent on missing dir
  - `TestGlobalPermissionCleanup` (4) — tilde + absolute perms removed, other settings preserved, no permissions section
  - `TestClaudeMdCleanup` (6) — both blocks removed, other content preserved, empty file deleted, no claude.md, no trailing whitespace
  - `TestGitignoreCleanup` (5) — entry removed, comment removed, other entries preserved, empty deleted, no parent repo
  - `TestRuntimeCleanup` (2) — pending dir removed, missing dir safe
  - `TestLocalSettingsNote` (2) — tilde and absolute paths in output
  - `TestAllFlag` (5) — cleans local tilde/absolute perms, preserves other perms, default doesn't clean, no file safe
  - `TestIdempotency` (2) — double run safe, double run with --all
  - `TestOutputMessages` (5) — confirms skill dir, permissions, CLAUDE.md, .gitignore, runtime cleanup

## Files modified
- `uninstall.sh` — rewrote with 6 cleanup steps + --all flag
- `tests/test_uninstall.py` — new test file (33 tests)
- `tests/conftest.py` — added `uninstall_sandbox` fixture, `run_uninstall()` helper, constants
