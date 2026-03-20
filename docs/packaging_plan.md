# Plan: Package claude-notifications as an Installable Repo

## Context

The iMessage notification skill for Claude Code currently lives scattered across `~/.claude/skills/imessage-notify/` (scripts), `notifications-spike/docs/imessage-skill/` (docs), and `notifications-spike/docs/imessage-skill/test/` (tests). The goal is to consolidate everything into the `claude-notifications` repo at `https://github.com/wwg-internal/claude-notifications` so users can clone it and run a single command to install.

**Platform**: macOS only. The entire tool depends on Messages.app, AppleScript, and `~/Library/Messages/chat.db`. All shell scripts use BSD `sed -i ''` syntax. CI runners must be macOS.

## User Experience

```bash
git clone https://github.com/wwg-internal/claude-notifications.git
cd claude-notifications
./install.sh
```

Or non-interactive:
```bash
./install.sh --phone +13522339160
```

The installer prompts for the phone number (or accepts `--phone`), copies scripts, injects permissions, checks FDA, and runs a verification test — all in one command.

## Repo Structure

```
claude-notifications/
├── CODEOWNERS                          # (existing)
├── LICENSE                             # Internal/proprietary notice
├── README.md                           # User-facing install + usage guide
├── CLAUDE.md                           # Instructions for Claude Code sessions in this repo
├── install.sh                          # One-command installer (interactive or --phone flag)
├── uninstall.sh                        # Clean removal of skill files + permissions
├── pyproject.toml                      # Test dependencies (pytest) + project metadata
├── src/
│   └── imessage-notify/
│       ├── send.sh                     # Send tagged iMessage (arg or stdin mode)
│       ├── notify.sh                   # Send + wait for reply
│       ├── read.sh                     # Poll chat.db for replies
│       ├── check_fda.sh               # Verify Full Disk Access
│       ├── hook_notify.sh             # Claude Code hook wrapper (debounced, requires jq)
│       ├── whitelist_commands.sh      # Inject permissions + configure RECIPIENT
│       ├── SKILL.md                    # LLM-facing skill protocol (Claude reads this)
│       └── README.md                   # Technical reference for the scripts
├── tests/
│   ├── conftest.py                     # SKILL_DIR, two named sandbox fixtures, shared helpers
│   ├── test_whitelist_commands.py      # 29 tests: phone normalization, permissions, RECIPIENT
│   └── test_imessage_scripts.py        # 54 tests: send/notify/read, stdin, escaping, etc.
├── docs/
│   ├── packaging_plan.md               # This plan
│   ├── setup.md                        # Detailed manual setup guide
│   ├── quickstart.md                   # 5-minute quick start
│   └── demo.md                         # Interactive demo walkthrough
└── .github/
    └── workflows/
        └── test.yml                    # CI: pytest on macos-14 runner
```

**Intentionally excluded**: `notifications-spike/docs/imessage-skill/imessage_skill_plan.md` — historical spike planning artifact, not user-facing.

## Files to Create/Migrate

### New Files

#### `install.sh` — One-Command Installer

Supports two modes:
- **Interactive**: `./install.sh` — prompts for phone number via `read -p`
- **Non-interactive**: `./install.sh --phone +13522339160` — skips prompt
- **Help**: `./install.sh --help` — prints usage

Behavior:

1. **Parse flags**: `--phone <number>`, `--help`. If no `--phone`, enter interactive mode.
2. **Check prerequisites**: macOS, Messages.app installed, `sqlite3`, `python3`. Warn (don't fail) if `jq` is missing — it's only needed for `hook_notify.sh`.
3. **Detect existing installation**: If `~/.claude/skills/imessage-notify/send.sh` exists with a non-placeholder RECIPIENT, offer to keep it (skip phone prompt) or overwrite.
4. **Prompt for phone number** (interactive mode only): Show accepted formats. Validate using the same normalization logic as `whitelist_commands.sh`. Loop until valid.
5. **Copy scripts**: Copy `src/imessage-notify/*.sh` and `src/imessage-notify/*.md` to `~/.claude/skills/imessage-notify/`
6. **Make executable**: `chmod +x ~/.claude/skills/imessage-notify/*.sh`
7. **Configure RECIPIENT + permissions**: Run installed `whitelist_commands.sh <phone>` from the current working directory.
8. **Write version stamp**: Write repo version (git tag or commit hash) to `~/.claude/skills/imessage-notify/.version`
9. **Check FDA**: Run `check_fda.sh`. If it fails, print instructions. Note: FDA failure is non-fatal for send (only read.sh needs FDA). Print instructions and continue.
10. **Remind about iMessage conversation**: Tell user to send themselves a test message in Messages.app if they haven't already.
11. **Verification test**: Run `send.sh "Installation test from claude-notifications"` and confirm exit code 0.
12. **Print CLAUDE.md snippet**: Output the iMessage Notifications block for `~/.claude/CLAUDE.md`. Include optional hook configuration JSON for `hook_notify.sh`.

Exit codes:
- 0: success
- 1: prerequisite check failed
- 2: user cancelled

**Idempotency**: Re-running `install.sh` is always safe. Partial installs from a prior failed run are overwritten. No rollback/trap cleanup needed.

#### `uninstall.sh` — Clean Removal
1. Remove `~/.claude/skills/imessage-notify/` directory
2. Remove iMessage permission entries from `~/.claude/settings.json` (global) using python3 JSON manipulation
3. Print note: local repo `.claude/settings.local.json` files are not modified (user can clean those manually)

#### `README.md` — User-Facing Guide
- One-liner install command (clone + `./install.sh`)
- Non-interactive mode: `./install.sh --phone +15551234567`
- What it does (send iMessages from Claude Code)
- Prerequisites (macOS, iMessage, FDA; optional: `jq` for hooks)
- Usage examples (send, notify, phone mode, mode switching)
- **Updating** section: `git pull && ./install.sh` (idempotent, preserves or re-prompts RECIPIENT)
- Troubleshooting section
- Link to detailed docs

#### `LICENSE`
- Internal/proprietary notice for wwg-internal org

#### `CLAUDE.md` — Repo-Level Instructions
- States this is the notification skill repo
- References test commands: `uv run pytest -m "not integration"`

#### `pyproject.toml` — Project Configuration
```toml
[project]
name = "claude-notifications"
version = "1.0.0"
description = "iMessage notifications for Claude Code"
requires-python = ">=3.10"

[dependency-groups]
dev = ["pytest>=9.0.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["integration: tests requiring Messages.app and iMessage"]
```

#### `.github/workflows/test.yml` — CI
- Runs on push to main and PRs
- **Pinned runner**: `macos-14` (BSD sed, sqlite3 compatibility)
- `uv run pytest -m "not integration"` (unit tests only)

#### `tests/conftest.py` — Shared Fixtures and Helpers

Defines:
- `SKILL_DIR = Path(__file__).parent.parent / "src" / "imessage-notify"` — all tests reference this, works from any cwd and in CI
- `EXPECTED_PERMISSIONS` — the 4 permission strings (these reference `~/.claude/skills/` paths because they validate the *installer's output format*, not the repo layout)
- **`script_sandbox` fixture** — for `test_imessage_scripts.py`: copies all `*.sh` via glob, creates a fake git repo, creates an isolated `PENDING_DIR` in tmp_path (never writes to real `/tmp/`). Returns keys: `skill`, `repo`, `pending`, `send_sh`, `notify_sh`, `read_sh`.
- **`whitelist_sandbox` fixture** — for `test_whitelist_commands.py`: creates a fake `$HOME` with `.claude/skills/imessage-notify/` tree, copies scripts + whitelist, patches `HOME` env var, creates global/local settings paths. Returns keys: `repo`, `home`, `skill`, `script`, `global_settings`, `local_settings`, `send_sh`, `read_sh`.
- Shared helpers: `run_send()`, `run_whitelist()`, `read_settings()`, `get_recipient()`, `patch_send_sh()`

**PENDING_DIR isolation guarantee**: Both sandbox fixtures create pending dirs under `tmp_path`. No test ever writes to `/tmp/imessage-notify-pending/`.

### Migrated Files (from existing locations)

| Source | Destination | Changes |
|--------|------------|---------|
| `~/.claude/skills/imessage-notify/send.sh` | `src/imessage-notify/send.sh` | Replace hardcoded RECIPIENT with `CHANGE_ME` placeholder |
| `~/.claude/skills/imessage-notify/notify.sh` | `src/imessage-notify/notify.sh` | None |
| `~/.claude/skills/imessage-notify/read.sh` | `src/imessage-notify/read.sh` | Replace hardcoded RECIPIENT with `CHANGE_ME` placeholder |
| `~/.claude/skills/imessage-notify/check_fda.sh` | `src/imessage-notify/check_fda.sh` | None |
| `~/.claude/skills/imessage-notify/hook_notify.sh` | `src/imessage-notify/hook_notify.sh` | None |
| `~/.claude/skills/imessage-notify/whitelist_commands.sh` | `src/imessage-notify/whitelist_commands.sh` | None |
| `~/.claude/skills/imessage-notify/SKILL.md` | `src/imessage-notify/SKILL.md` | None |
| `~/.claude/skills/imessage-notify/README.md` | `src/imessage-notify/README.md` | None |
| `notifications-spike/docs/imessage-skill/test/test_whitelist_commands.py` | `tests/test_whitelist_commands.py` | Replace `SKILL_DIR` with conftest import, rename fixture to `whitelist_sandbox` |
| `notifications-spike/docs/imessage-skill/test/test_imessage_scripts.py` | `tests/test_imessage_scripts.py` | Replace `SKILL_DIR` with conftest import, rename fixture to `script_sandbox`, extract helpers to conftest |
| `notifications-spike/docs/imessage-skill/imessage-setup.md` | `docs/setup.md` | Update paths to new repo structure, reference `install.sh` as primary method |
| `notifications-spike/docs/imessage-skill/imessage-quickstart.md` | `docs/quickstart.md` | Simplify: installer handles most steps. Update paths. |
| `notifications-spike/docs/imessage-skill/imessage-demo.md` | `docs/demo.md` | Minor path updates |

## Implementation Steps

### Step 1: Scaffold repo structure
- Create directory tree: `src/imessage-notify/`, `tests/`, `docs/`, `.github/workflows/`
- Create `pyproject.toml`, `CLAUDE.md`, `LICENSE`

### Step 2: Migrate scripts to `src/imessage-notify/`
- Copy all `.sh` and `.md` files from `~/.claude/skills/imessage-notify/`
- Replace hardcoded RECIPIENT in `send.sh` and `read.sh` with `CHANGE_ME` placeholder
- Ensure all scripts have `+x` permission

### Step 3: Write `install.sh`
- Parse `--phone` and `--help` flags
- Check prerequisites (macOS, Messages.app, sqlite3, python3; warn on missing jq)
- Detect existing RECIPIENT, offer to keep or overwrite
- Interactive phone prompt with format validation (or use `--phone` value)
- Copy scripts, run `whitelist_commands.sh`, write `.version` stamp
- Check FDA (non-fatal), remind about iMessage conversation
- Verification test, print CLAUDE.md + optional hook config snippet

### Step 4: Write `uninstall.sh`
- Remove `~/.claude/skills/imessage-notify/`
- Clean global `settings.json` permissions via python3

### Step 5: Migrate and refactor tests
- Create `tests/conftest.py` with `SKILL_DIR`, `EXPECTED_PERMISSIONS`, two named fixtures (`script_sandbox`, `whitelist_sandbox`), shared helpers
- Migrate `test_whitelist_commands.py`: update imports, rename fixture
- Migrate `test_imessage_scripts.py`: update imports, rename fixture, extract helpers
- Ensure no test writes to real `/tmp/imessage-notify-pending/`
- Verify all 83 tests pass

### Step 6: Migrate docs
- Copy 3 doc files (setup, quickstart, demo)
- Update all paths to reference new repo structure
- Simplify quickstart to reference `./install.sh` as primary

### Step 7: Write `README.md`
- Installation (clone + `./install.sh` or `--phone` mode)
- Updating section (`git pull && ./install.sh`)
- Usage examples
- Troubleshooting
- Prerequisites (including optional `jq`)

### Step 8: Write CI workflow
- `.github/workflows/test.yml`
- Pinned to `macos-14` runner
- `uv run pytest -m "not integration"`

### Step 9: End-to-end verification
- Run `./install.sh` from the new repo — verify scripts installed, permissions injected, test message received
- Run `./install.sh` again — verify idempotent (no errors, RECIPIENT preserved)
- Verify all 83 tests pass
- Run `./uninstall.sh` — confirm clean removal
- Fresh clone → `./install.sh --phone <number>` → verify phone mode works in another repo

## Key Design Decisions

1. **Bash installer, not Python package**: The skill is shell scripts. A bash installer is the natural choice. Python is only needed for tests and the JSON manipulation in `whitelist_commands.sh`.

2. **Placeholder RECIPIENT in source**: Source scripts in `src/` use `CHANGE_ME`. The installer configures the real value during setup. No personal data committed.

3. **`src/` as source-of-truth**: Scripts live in `src/imessage-notify/` and are copied to `~/.claude/skills/imessage-notify/` by the installer. Updates: `git pull && ./install.sh` (idempotent).

4. **Tests reference `src/` not `~/.claude/`**: Unit tests run against the repo's copy via `SKILL_DIR = Path(__file__).parent.parent / "src" / "imessage-notify"`. Works in CI without installation. `EXPECTED_PERMISSIONS` strings still reference `~/.claude/skills/` paths because they validate the installer's output format.

5. **macOS-only, explicitly**: BSD `sed -i ''`, AppleScript, Messages.app, `chat.db` — all macOS-specific. CI pinned to `macos-14`.

6. **Hook config is opt-in**: `install.sh` copies `hook_notify.sh` but does not auto-inject hook configuration into `settings.json`. The CLAUDE.md snippet printed at the end includes optional hook config for users who want it.

7. **Idempotent installer, no rollback**: Re-running `install.sh` is always safe. Partial installs from prior failures are simply overwritten on next run. No trap cleanup complexity needed.

## Verification

1. `uv run pytest -m "not integration"` — all 83 unit tests pass
2. `./install.sh --phone <number>` — non-interactive: scripts installed, permissions injected, test message received
3. `./install.sh` — interactive: detects existing RECIPIENT, offers to keep
4. `./install.sh` again — idempotent: no errors
5. `./uninstall.sh` — clean removal verified
6. Fresh clone → `./install.sh` → phone mode works in another repo