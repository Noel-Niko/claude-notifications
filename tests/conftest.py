"""Shared fixtures and helpers for claude-notifications tests.

Defines:
- SKILL_DIR: Path to source scripts in src/imessage-notify/
- EXPECTED_PERMISSIONS: The 4 permission strings the installer injects
- script_sandbox: Isolated sandbox for send.sh/notify.sh/read.sh tests
- whitelist_sandbox: Isolated sandbox for whitelist_commands.sh tests
- Shared helpers: run_send(), run_whitelist(), read_settings(), get_recipient(), patch_send_sh()
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

# Source scripts in the repo (not ~/.claude/skills/)
SKILL_DIR = Path(__file__).parent.parent / "src" / "imessage-notify"

# Permission strings reference ~/.claude/skills/ paths because they validate
# the installer's output format, not the repo layout
EXPECTED_PERMISSIONS = [
    "Bash(~/.claude/skills/imessage-notify/notify.sh *)",
    "Bash(~/.claude/skills/imessage-notify/send.sh *)",
    "Bash(~/.claude/skills/imessage-notify/read.sh *)",
    "Bash(~/.claude/skills/imessage-notify/check_fda.sh)",
    "Bash(cat ~/.claude/skills/imessage-notify/*)",
    "Read(~/.claude/skills/imessage-notify/*)",
]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def script_sandbox(tmp_path):
    """Isolated sandbox for send.sh/notify.sh/read.sh tests.

    Copies all *.sh scripts, creates a fake git repo, and creates an
    isolated PENDING_DIR under tmp_path (never writes to real /tmp/).

    Returns dict with keys: skill, repo, pending, send_sh, notify_sh, read_sh
    """
    skill = tmp_path / "skill"
    skill.mkdir()

    # Copy all scripts
    for script in SKILL_DIR.glob("*.sh"):
        shutil.copy2(script, skill / script.name)

    # Create a fake git repo so send.sh can detect repo name
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    # Use a unique pending dir for isolation
    pending = tmp_path / "pending"
    pending.mkdir()

    return {
        "skill": skill,
        "repo": repo,
        "pending": pending,
        "send_sh": skill / "send.sh",
        "notify_sh": skill / "notify.sh",
        "read_sh": skill / "read.sh",
    }


@pytest.fixture()
def whitelist_sandbox(tmp_path, monkeypatch):
    """Isolated sandbox for whitelist_commands.sh tests.

    Creates a fake $HOME with .claude/skills/imessage-notify/ tree,
    copies scripts + whitelist, patches HOME env var.

    Returns dict with keys: repo, home, skill, script, global_settings,
    local_settings, send_sh, read_sh
    """
    repo = tmp_path / "fake-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    home = tmp_path / "home"
    home.mkdir()

    skill = home / ".claude" / "skills" / "imessage-notify"
    skill.mkdir(parents=True)

    # Copy real scripts into sandbox skill dir
    for script in ["send.sh", "read.sh", "notify.sh", "check_fda.sh"]:
        src = SKILL_DIR / script
        if src.exists():
            shutil.copy2(src, skill / script)

    # Copy whitelist_commands.sh itself
    shutil.copy2(SKILL_DIR / "whitelist_commands.sh", skill / "whitelist_commands.sh")

    # Global settings location
    global_settings = home / ".claude" / "settings.json"

    monkeypatch.setenv("HOME", str(home))

    return {
        "repo": repo,
        "home": home,
        "skill": skill,
        "script": skill / "whitelist_commands.sh",
        "global_settings": global_settings,
        "local_settings": repo / ".claude" / "settings.local.json",
        "send_sh": skill / "send.sh",
        "read_sh": skill / "read.sh",
    }


# =============================================================================
# Shared Helpers
# =============================================================================


def patch_send_sh(sandbox, pending_dir=None, mock_applescript=True):
    """Patch send.sh to use sandbox pending dir and optionally mock AppleScript.

    Returns the path to the patched script.
    """
    send_sh = sandbox["send_sh"]
    content = send_sh.read_text()

    # Replace PENDING_DIR
    if pending_dir:
        content = content.replace(
            'PENDING_DIR="/tmp/imessage-notify-pending"',
            f'PENDING_DIR="{pending_dir}"',
        )

    # Mock the AppleScript and pgrep calls for unit testing
    if mock_applescript:
        # Replace pgrep check with always-true
        content = content.replace(
            'if ! pgrep -x "Messages" >/dev/null; then',
            "if false; then",
        )
        # Replace osascript call with a no-op that succeeds
        content = re.sub(
            r"applescript_output=\$\(osascript.*?\n.*?\n.*?\n.*?\n\" 2>&1\)",
            'applescript_output="OK"',
            content,
            flags=re.DOTALL,
        )
        content = content.replace(
            "applescript_exit=$?",
            "applescript_exit=0",
        )

    send_sh.write_text(content)
    return send_sh


def run_send(sandbox, *args, stdin_text=None, mock=True):
    """Run send.sh with optional args and stdin."""
    pending = str(sandbox["pending"])
    patch_send_sh(sandbox, pending_dir=pending, mock_applescript=mock)

    cmd = [str(sandbox["send_sh"]), *args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(sandbox["repo"]),
        input=stdin_text,
    )
    return result


def run_whitelist(sandbox, *args, expect_fail=False):
    """Run whitelist_commands.sh in the sandbox repo with optional args."""
    result = subprocess.run(
        [str(sandbox["script"]), *args],
        capture_output=True,
        text=True,
        cwd=str(sandbox["repo"]),
        env={**os.environ, "HOME": str(sandbox["home"])},
    )
    if not expect_fail:
        assert result.returncode == 0, (
            f"Script failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def read_settings(path):
    """Read and parse a settings JSON file."""
    with open(path) as f:
        return json.load(f)


def get_recipient(script_path):
    """Extract the RECIPIENT value from a script file."""
    for line in script_path.read_text().splitlines():
        if line.startswith("RECIPIENT="):
            return line.split("=", 1)[1].strip('"')
    return None
