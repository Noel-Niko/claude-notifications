# Plan: Add iMessage Activation Check to Installer

## Status: Complete

## Context

A user installed claude-notifications but iMessage wasn't activated on their Mac. The installer passed (Messages.app exists) but the tool failed at runtime. Added a reliable iMessage activation check during installation.

## Detection Mechanism

AppleScript service query — no FDA required:

```bash
osascript -e 'tell application "Messages" to count of (services whose service type is iMessage)'
```

- Returns >=1 if iMessage is signed in
- Returns 0 if iMessage is not activated
- Falls back to warning if query fails (automation permission denied)

## Exit Codes

- `0` — Messages.app found, iMessage active
- `1` — Messages.app not found (hard fail, stops install)
- `2` — Messages.app found but iMessage not activated (warning, install continues)

## Files Changed

| File | Action |
|------|--------|
| `src/imessage-notify/check_imessage.sh` | Created — AppleScript-based detection |
| `tests/test_check_imessage.py` | Created — 23 unit tests + integration test |
| `install.sh` | Modified — prereq check + Step 10 error message |
| `src/imessage-notify/whitelist_commands.sh` | Modified — added permission entry |
| `uninstall.sh` | Modified — added 3 permission entries (1 new + 2 missing) |
| `tests/conftest.py` | Modified — EXPECTED_PERMISSIONS + whitelist_sandbox |
| `tests/test_imessage_scripts.py` | Modified — TestScriptPermissions |

## Steps Completed

- [x] Write tests (TDD red phase)
- [x] Create stub, verify tests fail
- [x] Implement check_imessage.sh (TDD green phase)
- [x] Update install.sh
- [x] Update permissions/whitelist files
- [x] Fix uninstall.sh discrepancy (was missing cat/Read entries)
- [x] Run full suite — 105 passed, 0 failed
