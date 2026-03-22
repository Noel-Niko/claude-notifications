
# To Use
 In Claude Code,
- Starting NEW SESSION, 
  - Recommended first command "Review Claude.md and switch to iMessage mode"
- Within an Existing Session
 - Say "use iMessage", "switch to iMessage", or mention "phone" / "away from computer" to enable phone mode.
   - Claude will use notify.sh for all approvals instead of IDE prompts.
   - Reply 'switch to IDE' on your phone to switch back.

_____

# claude-notifications

iMessage notifications for Claude Code. Send messages to your phone, get approvals via iMessage, and switch between IDE and phone approval modes dynamically.

## Install

```bash
git clone https://github.com/wwg-internal/claude-notifications.git
cd claude-notifications
./install.sh
```

Or non-interactive:
```bash
./install.sh --phone +15551234567
./install.sh --phone your.email@icloud.com
```

The installer prompts for your phone number, copies scripts, configures permissions, checks Full Disk Access, sends a test message, and offers an interactive demo.

## Installation via Internal Artifactory (pip)

The `claude-notifications` package is published to Grainger's internal JFrog Artifactory.

- **Package**: https://graingerinc.jfrog.io/ui/packages/pypi:%2F%2Fclaude-notifications/1.0.0

### Step 1: Configure pip Authentication

This is a one-time setup per machine.

1. Navigate to [LaunchPoint - JFrog Artifactory Python Setup](https://launchpoint.internal.grainger.com/docs/default/component/nextgen-platform-user-manual/jfrog-artifactory/local-machine-setup/python-pip/) and generate your personal authentication token.

2. Configure `~/.pip/pip.conf`:

```bash
mkdir -p ~/.pip

# Replace YOUR_EMAIL and YOUR_TOKEN with values from LaunchPoint
cat > ~/.pip/pip.conf << 'EOF'
[global]
index-url = https://YOUR_EMAIL@grainger.com:YOUR_TOKEN@graingerinc.jfrog.io/artifactory/api/pypi/pypi-shared-virtual/simple
EOF

# Verify configuration
pip config list
```

### Step 2: Install the Package

```bash
# uv
uv add claude-notifications==1.0.0

# pip
pip install claude-notifications==1.0.0
```

Then run the installer to configure scripts and permissions:

```bash
cd $(python -c "import importlib.resources; print(importlib.resources.files('claude_notifications'))")
./install.sh
```

### Step 3: Upgrade to Latest Version

```bash
pip install --upgrade claude-notifications
```

### Troubleshooting Artifactory Installation

#### "Could not find a version that satisfies the requirement"

**Cause:** `pip.conf` not configured or authentication token expired.

1. Verify pip configuration: `pip config list`
2. Regenerate token from [LaunchPoint](https://launchpoint.internal.grainger.com/docs/default/component/nextgen-platform-user-manual/jfrog-artifactory/local-machine-setup/python-pip/)
3. Update `~/.pip/pip.conf` with new token

#### "401 Unauthorized" or "403 Forbidden"

**Cause:** Invalid or expired authentication token. Regenerate from [LaunchPoint](https://launchpoint.internal.grainger.com/docs/default/component/nextgen-platform-user-manual/jfrog-artifactory/local-machine-setup/python-pip/) and update `~/.pip/pip.conf`.

### Installation Methods Comparison

| Method | Use Case | Command |
|--------|----------|---------|
| **Artifactory (pip)** | Stable releases | `pip install claude-notifications` |
| **Git clone + install.sh** | Development, latest changes | `git clone ... && ./install.sh` |

## Prerequisites
![FDA.gif](docs/FDA.gif)
- **macOS** (Messages.app, AppleScript, sqlite3)
- **iMessage** account signed in to Messages.app
- **Full Disk Access** for your terminal app (required for reading replies)
- **python3** (for JSON permission injection)
- **jq** (optional, only needed for `hook_notify.sh`)

## What It Does

| Script | Purpose |
|--------|---------|
| `send.sh` | Fire-and-forget iMessage (no reply expected) |
| `notify.sh` | Send message and wait for reply via iMessage |
| `read.sh` | Poll chat.db for replies (used by notify.sh) |
| `check_fda.sh` | Verify Full Disk Access is granted |
| `whitelist_commands.sh` | Inject permissions + configure RECIPIENT |
| `hook_notify.sh` | Claude Code hook wrapper (debounced) |

## Usage

After installation, Claude Code automatically uses the skill via `~/.claude/skills/imessage-notify/SKILL.md`.

### Send a status update (fire-and-forget)
```bash
~/.claude/skills/imessage-notify/send.sh "Build succeeded. All 42 tests passed."
```

### Send and wait for reply
```bash
reply=$(~/.claude/skills/imessage-notify/notify.sh "Deploy to staging? Reply YES or NO." 300 10)
```

### Multiline messages (file mode)
```bash
# Write message to a temp file, then pass with -f:
~/.claude/skills/imessage-notify/send.sh -f /tmp/my-message.txt
~/.claude/skills/imessage-notify/notify.sh -f /tmp/my-message.txt 300 10
# The -f flag reads the file and deletes it after sending.
```

Stdin mode also works for simple cases:
```bash
echo "Short message" | ~/.claude/skills/imessage-notify/send.sh -
echo "Short question" | ~/.claude/skills/imessage-notify/notify.sh - 300 10
```

### Phone mode in Claude Code

Say **"use iMessage"**, **"switch to iMessage"**, or mention **"phone"** / **"away from computer"** in any Claude Code session. Claude will immediately switch to phone-only approvals using `notify.sh`. Reply **"switch to IDE"** on your phone to switch back.

## Per-Repo Permissions

For each new repo where you want phone mode, run:
```bash
cd /path/to/your/repo
~/.claude/skills/imessage-notify/whitelist_commands.sh
```

This injects wildcard permission entries so iMessage scripts don't require IDE approval.

## Updating

```bash
cd claude-notifications
git pull
./install.sh
```

The installer is idempotent. It detects your existing RECIPIENT and offers to keep it.

## Uninstall

```bash
./uninstall.sh
```

Removes `~/.claude/skills/imessage-notify/` and cleans global permissions.

## Multi-Session Support

Multiple Claude Code sessions can run simultaneously without cross-talk:
- Each message is tagged: `[repo-name|REQ-<unique-id>] message`
- Reply with the ID to target a specific session: `a1b2c3d4 yes`
- Plain replies go to the most recent pending request

## Architecture: Two-Layer Permission Problem and Solution

Phone mode requires two independent systems to cooperate. When either layer fails, the user experience breaks. This section documents the architecture, the problems, and how each is solved.

### Layer 1: LLM Instruction Layer

**What it is:** Claude Code reads `CLAUDE.md` and `SKILL.md` to decide *whether* to use iMessage for approvals vs. IDE prompts.

**Problem:** The LLM has no persistent state. It re-derives its behavioral mode from the conversation history every turn. After context compaction (`/compact`), long tool outputs, or many turns, the original "use iMessage" instruction gets diluted or lost. The LLM reverts to IDE mode silently.

Additionally, Task agents (subprocesses launched for parallel research) run with independent context. They have no awareness of the parent session's phone mode and cannot use iMessage.

**Solution:**
- **Automatic trigger keywords:** If the user mentions "iMessage", "phone", "away from computer", or "away from the compute" anywhere in their message, the LLM switches to phone mode immediately with no confirmation prompt. This eliminates the previous "offer phone mode" conditional that the LLM kept ignoring.
- **Post-compaction recovery:** After `/compact`, the LLM re-reads the iMessage section and sends a confirmation via `notify.sh` if phone mode was active.
- **Simplified instructions:** The CLAUDE.md and SKILL.md sections were rewritten to be shorter and more directive ("just switch") rather than conditional ("offer to switch if 3+ steps").

### Layer 2: CLI Tool Permission Layer

**What it is:** Claude Code's CLI gates every `Bash()` tool call through a permission check. Commands must match a whitelisted glob pattern, or the CLI shows an interactive "Do you want to proceed?" prompt in the IDE.

**Problem:** The permission system uses glob patterns where `*` does **not** match newlines. This creates a gap:

| Command | Matches `notify.sh *`? | Result |
|---------|----------------------|--------|
| `notify.sh "short msg" 600 10` | Yes | Runs without prompt |
| `notify.sh -f /tmp/file.txt 600 10` | Yes | Runs without prompt |
| `echo "msg" \| notify.sh - 600 10` | No (starts with `echo`) | **Blocked — IDE prompt** |
| `cat <<'EOF'\n...\nEOF \| notify.sh -` | No (multiline, starts with `cat`) | **Blocked — IDE prompt** |

The LLM tends to send long, detailed approval messages that span multiple lines. Before the `-f` flag existed, the only way to send multiline messages was via piped stdin (`echo "..." | notify.sh -` or `cat <<EOF | notify.sh -`). Both patterns fail to match the whitelisted glob, causing the IDE to prompt — which blocks indefinitely when the user is away from the computer.

**Solution: The `-f` flag.**

Both `send.sh` and `notify.sh` now accept `-f <filepath>`:
1. The LLM uses the **Write tool** (which requires no Bash permission) to create a temp file at `/tmp/imessage-notify-msg-{uuid}.txt`
2. The LLM runs `notify.sh -f /tmp/imessage-notify-msg-{uuid}.txt 600 10` — a **single-line command** that matches `notify.sh *`
3. The script reads the file, sends its contents as the message, and deletes the temp file

This completely bypasses the newline glob limitation. The Bash command is always one line regardless of message length, so it always matches the whitelisted pattern.

### Both Layers Must Be Configured

The `install.sh` script configures both layers:
- **Layer 1:** Appends the iMessage instructions block to `~/.claude/CLAUDE.md`
- **Layer 2:** Runs `whitelist_commands.sh` to inject permission patterns into `~/.claude/settings.json` and the repo's `.claude/settings.local.json`

If only one layer is configured, phone mode will partially fail:
- Layer 1 configured, Layer 2 not → LLM tries to use iMessage but every Bash command triggers an IDE prompt
- Layer 2 configured, Layer 1 not → Commands are whitelisted but the LLM never uses them (stays in IDE mode)

### Remaining Limitations

1. **Task agents are stateless.** When the LLM launches parallel Task agents (subprocesses for research, exploration, etc.), those agents run with independent context. They cannot use iMessage and have no awareness of phone mode. Only the parent session uses phone mode; Task agents work silently and return results to the parent.

2. **Context window pressure.** Even with simplified instructions, an extremely long session with many tool outputs can push the iMessage instructions far enough back that the LLM deprioritizes them. The post-compaction recovery rule mitigates this but does not eliminate it entirely.

3. **No programmatic mode persistence.** There is no API or config file that stores "current mode = phone." The mode exists only in the LLM's interpretation of the conversation. This is inherent to how Claude Code works — the LLM is stateless between turns and reconstructs context from the message history.

## Troubleshooting

### Messages not arriving
1. Check Messages.app is running and signed in
2. Verify Full Disk Access: `~/.claude/skills/imessage-notify/check_fda.sh`
3. Test manually: `~/.claude/skills/imessage-notify/send.sh "test"`

### "Do you want to proceed?" keeps appearing
```bash
cd /path/to/your/repo
~/.claude/skills/imessage-notify/whitelist_commands.sh
```

If it still appears, make sure you're using `-f` file mode for multiline messages (not heredoc or piped stdin with newlines).

### Multiline messages trigger approval prompts
Use file mode instead of stdin/heredoc:
```bash
# Write your message to a file first, then:
~/.claude/skills/imessage-notify/notify.sh -f /tmp/my-message.txt 600 10
```

The glob wildcard `*` in the whitelisted pattern does not match newlines, so piped multiline commands will always trigger prompts. The `-f` flag avoids this by keeping the command on a single line.

## Development

### Run tests
```bash
uv run pytest -m "not integration"
```

### Run integration tests (sends real iMessages)
```bash
uv run pytest -m integration
```

## Documentation

- [Quick Start](docs/quickstart.md) - 5-minute setup
- [Setup Guide](docs/setup.md) - Detailed installation
- [Demo](docs/demo.md) - Interactive walkthrough
- [Packaging Plan](docs/packaging_plan.md) - Design document