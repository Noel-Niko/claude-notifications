"""Shared fixtures and helpers for claude-notifications tests.

Defines:
- SKILL_DIR: Path to source scripts in src/imessage-notify/
- EXPECTED_PERMISSIONS: The 7 permission strings the installer injects
- script_sandbox: Isolated sandbox for send.sh/notify.sh/read.sh tests
- whitelist_sandbox: Isolated sandbox for whitelist_commands.sh tests
- uninstall_sandbox: Isolated sandbox for uninstall.sh tests
- Shared helpers: run_send(), run_whitelist(), run_uninstall(),
  read_settings(), get_recipient(), patch_send_sh()
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
    "Bash(~/.claude/skills/imessage-notify/check_imessage.sh)",
    "Bash(cat ~/.claude/skills/imessage-notify/*)",
    "Read(~/.claude/skills/imessage-notify/*)",
]


def expected_absolute_permissions(home_dir):
    """Generate expected absolute-path permission patterns for a given HOME.

    Sub-agents may not resolve ~ correctly, so absolute paths are injected
    alongside the tilde versions as defense-in-depth.
    """
    skill = f"{home_dir}/.claude/skills/imessage-notify"
    return [
        f"Bash({skill}/notify.sh *)",
        f"Bash({skill}/send.sh *)",
        f"Bash({skill}/read.sh *)",
        f"Bash({skill}/check_fda.sh)",
        f"Bash({skill}/check_imessage.sh)",
        f"Bash(cat {skill}/*)",
        f"Read({skill}/*)",
    ]


# Path to the repo's uninstall.sh
UNINSTALL_SCRIPT = Path(__file__).parent.parent / "uninstall.sh"

# Markers used by install.sh in CLAUDE.md
POST_COMPACT_MARKER = "CRITICAL — POST-COMPACT RULE"
IMESSAGE_MARKER = "## iMessage Notifications (MANDATORY)"

# Sample CLAUDE.md with user content + both installer blocks
SAMPLE_CLAUDE_MD = """\
> **CRITICAL — POST-COMPACT RULE:** After every `/compact`, you MUST re-read \
this file (`~/.claude/CLAUDE.md`) in full using the Read tool **before** doing \
anything else. Do not rely on the compacted summary for these rules — the \
summary may omit or simplify critical constraints. Re-reading ensures no \
instructions are lost. This rule itself must be preserved in the compact \
summary so it triggers the re-read.

# CLAUDE.md

## Code Style & Practices
- Always follow SOLID principles, clean code, and DRY practices.
- Use TDD as the development pattern.

## Workflow
- Do not commit code. Leave all commits to the user.

## iMessage Notifications (MANDATORY)

**Two modes:** IDE mode (default) and Phone mode.

**Automatic phone mode triggers — no confirmation needed:**
If the user mentions "iMessage", "phone", "away from computer", \
**immediately switch to phone mode**.

**Setup:**
- Read `~/.claude/skills/imessage-notify/SKILL.md` for the full protocol
- If scripts fail, run `~/.claude/skills/imessage-notify/check_fda.sh`
"""

# CLAUDE.md with only installer blocks (file should be deleted after cleanup)
SAMPLE_CLAUDE_MD_INSTALLER_ONLY = """\
> **CRITICAL — POST-COMPACT RULE:** After every `/compact`, you MUST re-read \
this file (`~/.claude/CLAUDE.md`) in full using the Read tool **before** doing \
anything else.

## iMessage Notifications (MANDATORY)

**Two modes:** IDE mode (default) and Phone mode.

**Setup:**
- Read `~/.claude/skills/imessage-notify/SKILL.md` for the full protocol
"""


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
    for script in [
        "send.sh",
        "read.sh",
        "notify.sh",
        "check_fda.sh",
        "check_imessage.sh",
    ]:
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


@pytest.fixture()
def uninstall_sandbox(tmp_path, monkeypatch):
    """Isolated sandbox for uninstall.sh tests.

    Creates a fully installed environment matching what install.sh produces:
    - Fake HOME with skill dir, global settings, CLAUDE.md
    - Parent git repo with .gitignore containing claude-notifications/ entry
    - Clone dir with uninstall.sh
    - Runtime pending dir
    - Per-repo local settings in parent repo
    """
    home = tmp_path / "home"
    home.mkdir()

    # Installed skill directory
    skill = home / ".claude" / "skills" / "imessage-notify"
    skill.mkdir(parents=True)
    for script in SKILL_DIR.glob("*.sh"):
        shutil.copy2(script, skill / script.name)
    for md_file in SKILL_DIR.glob("*.md"):
        shutil.copy2(md_file, skill / md_file.name)
    (skill / ".version").write_text("v1.0.0-test\n")

    # Global settings with tilde + absolute permissions + other entries
    global_settings = home / ".claude" / "settings.json"
    all_perms = list(EXPECTED_PERMISSIONS) + expected_absolute_permissions(
        str(home)
    )
    global_settings.write_text(
        json.dumps(
            {
                "env": {"SOME_VAR": "preserved"},
                "permissions": {"allow": all_perms + ["Bash(git status)"]},
            },
            indent=2,
        )
        + "\n"
    )

    # CLAUDE.md with both installer blocks + user content
    claude_md = home / ".claude" / "CLAUDE.md"
    claude_md.write_text(SAMPLE_CLAUDE_MD)

    # Parent git repo
    parent_repo = tmp_path / "parent-repo"
    parent_repo.mkdir()
    subprocess.run(["git", "init", "-q", str(parent_repo)], check=True)

    # Clone dir inside parent repo
    clone_dir = parent_repo / "claude-notifications"
    clone_dir.mkdir()

    # Copy uninstall.sh into clone dir
    shutil.copy2(UNINSTALL_SCRIPT, clone_dir / "uninstall.sh")
    (clone_dir / "uninstall.sh").chmod(0o755)

    # Parent .gitignore with notification entry + other entries
    parent_gitignore = parent_repo / ".gitignore"
    parent_gitignore.write_text(
        "node_modules/\n"
        "*.pyc\n"
        "\n"
        "# Claude notifications (cloned installer)\n"
        "claude-notifications/\n"
    )

    # Local settings in parent repo (for --all flag)
    local_settings = parent_repo / ".claude" / "settings.local.json"
    local_settings.parent.mkdir(parents=True, exist_ok=True)
    local_perms = list(EXPECTED_PERMISSIONS) + expected_absolute_permissions(
        str(home)
    )
    local_settings.write_text(
        json.dumps(
            {"permissions": {"allow": local_perms + ["Bash(npm test)"]}},
            indent=2,
        )
        + "\n"
    )

    # Runtime pending dir with content
    pending = tmp_path / "pending"
    pending.mkdir()
    req_dir = pending / "REQ-abc123"
    req_dir.mkdir()
    (req_dir / "claim").write_text("claimed")

    monkeypatch.setenv("HOME", str(home))

    return {
        "home": home,
        "skill": skill,
        "global_settings": global_settings,
        "claude_md": claude_md,
        "parent_repo": parent_repo,
        "clone_dir": clone_dir,
        "script": clone_dir / "uninstall.sh",
        "parent_gitignore": parent_gitignore,
        "local_settings": local_settings,
        "pending": pending,
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


def get_aliases(script_path):
    """Extract the RECIPIENT_ALIASES value from a script file (read.sh).

    Returns the raw string value (space-separated addresses), or None if not found.
    """
    for line in script_path.read_text().splitlines():
        if line.startswith("RECIPIENT_ALIASES="):
            return line.split("=", 1)[1].strip('"')
    return None


def run_uninstall(sandbox, *args, expect_fail=False):
    """Run uninstall.sh in the sandbox clone dir."""
    env = {
        **os.environ,
        "HOME": str(sandbox["home"]),
        "PENDING_DIR": str(sandbox["pending"]),
    }
    result = subprocess.run(
        [str(sandbox["script"]), *args],
        capture_output=True,
        text=True,
        cwd=str(sandbox["clone_dir"]),
        env=env,
    )
    if not expect_fail:
        assert result.returncode == 0, (
            f"Script failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result
