"""Shared fixtures and helpers for claude-notifications tests.

Defines:
- SKILL_DIR: Path to source scripts in src/imessage-notify/
- EXPECTED_PERMISSIONS: The 7 permission strings the installer injects
- script_sandbox: Isolated sandbox for send.sh/notify.sh/read.sh tests
- whitelist_sandbox: Isolated sandbox for whitelist_commands.sh tests
- uninstall_sandbox: Isolated sandbox for uninstall.sh tests
- permission_gate_sandbox: Isolated sandbox for permission_gate.sh tests
- chat_db: Isolated SQLite database mimicking chat.db schema
- Shared helpers: run_send(), run_whitelist(), run_uninstall(),
  read_settings(), get_recipient(), patch_send_sh(), run_permission_gate(),
  load_query_messages_module(), TYPEDSTREAM_BLOBS
"""

import importlib.util
import json
import os
import re
import shutil
import sqlite3
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
    all_perms = list(EXPECTED_PERMISSIONS) + expected_absolute_permissions(str(home))
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
    local_perms = list(EXPECTED_PERMISSIONS) + expected_absolute_permissions(str(home))
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


# =============================================================================
# Permission Gate (hook) support
# =============================================================================

# Mock notify.sh that returns a configurable reply without sending real iMessages.
# Controlled by env vars:
#   MOCK_NOTIFY_REPLY: "yes", "no", "timeout", "fail", or any string
#   MOCK_NOTIFY_CAPTURE: file path to write the captured message to
MOCK_NOTIFY_SH = """\
#!/usr/bin/env bash
# Mock notify.sh for testing permission_gate.sh
if [ "${1:-}" = "-f" ]; then
  msg="$(cat "$2")"
  rm -f "$2"
else
  msg="${1:-}"
fi
if [ -n "${MOCK_NOTIFY_CAPTURE:-}" ]; then
  echo "$msg" > "$MOCK_NOTIFY_CAPTURE"
fi
case "${MOCK_NOTIFY_REPLY:-yes}" in
  timeout) echo "TIMEOUT: No reply received within 300s" >&2; exit 1 ;;
  fail) echo "ERROR: Failed to send iMessage" >&2; exit 1 ;;
  *) echo "${MOCK_NOTIFY_REPLY:-yes}"; exit 0 ;;
esac
"""


@pytest.fixture()
def permission_gate_sandbox(tmp_path):
    """Isolated sandbox for permission_gate.sh tests.

    Copies permission_gate.sh from source and creates a mock notify.sh
    that returns configurable replies without sending real iMessages.

    Returns dict with keys: skill, gate_sh, flag_file, capture_file
    """
    skill = tmp_path / "skill"
    skill.mkdir()

    # Copy permission_gate.sh from source (may not exist yet during TDD)
    gate_src = SKILL_DIR / "permission_gate.sh"
    if gate_src.exists():
        shutil.copy2(gate_src, skill / "permission_gate.sh")
        (skill / "permission_gate.sh").chmod(0o755)

    # Create mock notify.sh
    mock_notify = skill / "notify.sh"
    mock_notify.write_text(MOCK_NOTIFY_SH)
    mock_notify.chmod(0o755)

    # Flag file path (not created by default — tests create it as needed)
    flag_file = tmp_path / "phone-mode-flag"

    # Capture file for inspecting what message was sent to notify.sh
    capture_file = tmp_path / "notify-capture"

    return {
        "skill": skill,
        "gate_sh": skill / "permission_gate.sh",
        "flag_file": flag_file,
        "capture_file": capture_file,
    }


def run_permission_gate(sandbox, stdin_json, reply="yes", env_extra=None):
    """Run permission_gate.sh with given stdin JSON and mock notify reply.

    Args:
        sandbox: permission_gate_sandbox dict
        stdin_json: dict to serialize as JSON stdin, or raw string
        reply: mock notify.sh reply ("yes", "no", "timeout", "fail", or any string)
        env_extra: additional env vars to set

    Returns:
        subprocess.CompletedProcess
    """
    env = {
        **os.environ,
        "PHONE_MODE_FLAG": str(sandbox["flag_file"]),
        "MOCK_NOTIFY_REPLY": reply,
        "MOCK_NOTIFY_CAPTURE": str(sandbox["capture_file"]),
    }
    if env_extra:
        env.update(env_extra)

    stdin_text = json.dumps(stdin_json) if isinstance(stdin_json, dict) else stdin_json

    result = subprocess.run(
        [str(sandbox["gate_sh"])],
        capture_output=True,
        text=True,
        input=stdin_text,
        env=env,
    )
    return result


# =============================================================================
# attributedBody / typedstream test fixtures
# =============================================================================

# Real typedstream blobs captured from macOS Sequoia chat.db.
# Each is a hex-encoded NSAttributedString serialized via Apple's typedstream format.
TYPEDSTREAM_BLOBS = {
    # Short user reply: "Yes" (is_from_me=0, no leading control chars)
    "short_user_reply": {
        "hex": (
            "040b73747265616d747970656481e803840140848484124e534174747269627574"
            "6564537472696e67008484084e534f626a656374008592848484084e5353747269"
            "6e67019484012b03596573868402694901039284848"
            "40c4e5344696374696f6e617279009484016901928496961d5f5f6b494d4d657373"
            "616765506172744174747269627574654e616d658692848484084e534e756d626572"
            "008484074e5356616c7565009484012a84999900868686"
        ),
        "expected_text": "Yes",
        "is_from_me": 0,
    },
    # User reply with leading \x00 control char (is_from_me=0)
    "user_reply_control_chars": {
        "hex": (
            "040b73747265616d747970656481e803840140848484124e534174747269627574"
            "6564537472696e67008484084e534f626a656374008592848484084e5353747269"
            "6e67019484012b811d014920616464656420746865204"
            "7656e6573697320636c69656e7420494420616e6420636c69656e742073656372"
            "657420746f2074686520646f7420454e562066696c6520627574206172656ee280"
            "997420776520737570706f73656420746f2062652067657474696e672074686f73"
            "65207768656e20776520736f757263652066726f6d20746865207661756c742061"
            "6e64204157533f2053776974636820746f204944206d6f646520616e6420776520"
            "77696c6c2064697363757373207468617420696d706c656d656e746174696f6e20"
            "7468656e2070726f76696465207465787420746f20636f6d706163742061732077"
            "65207072657061726520746f20706f727420746865204d4350206261636b656e64"
            "20736572766963652e868402694901811b01928484840c4e5344696374696f6e61"
            "7279009484016901928496961d5f5f6b494d4d657373616765506172744174747269"
            "627574654e616d658692848484084e534e756d626572008484074e5356616c756500"
            "9484012a84999900868686"
        ),
        "expected_text": (
            "I added the Genesis client ID and client secret to the dot ENV file "
            "but aren\u2019t we supposed to be getting those when we source from "
            "the vault and AWS? Switch to ID mode and we will discuss that "
            "implementation then provide text to compact as we prepare to port "
            "the MCP backend service."
        ),
        "is_from_me": 0,
    },
    # Claude-tagged message: [repo|REQ-xxx] (is_from_me=1)
    "claude_tagged": {
        "hex": (
            "040b73747265616d747970656481e803840140848484124e534174747269627574"
            "6564537472696e67008484084e534f626a656374008592848484084e5353747269"
            "6e67019484012b8143015b6461637363762d6576656e746272696467652d696d70"
            "6c656d656e746174696f6e2d706f637c5245512d61653433633965375d205b5065"
            "726d697373696f6e5d20436c617564652077616e747320746f3a0a52756e20636f"
            "6d6d616e643a2073716c69746533207e2f4c6962726172792f4d657373616765"
            "732f636861742e6462202253454c454354206d2e646174652c206d2e69735f6672"
            "6f6d5f6d652c206d2e746578742046524f4d206d657373616765206d204a4f494e"
            "20636861745f6d6573736167655f6a6f696e20636d6a204f4e206d2e524f574944"
            "203d20636d6a2e6d6573736167655f6964204a4f494e20636861742063204f4e20"
            "636d6a2e636861745f6964203d20632e524f57494420574845524520632e636861"
            "745f6964656e746966692e2e2e0a416c6c6f773f205265706c7920594553206f72"
            "204e4f2e868402694901814301928484840c4e5344696374696f6e617279009484"
            "016901928496961d5f5f6b494d4d657373616765506172744174747269627574654e"
            "616d658692848484084e534e756d626572008484074e5356616c7565009484012a"
            "84999900868686"
        ),
        "expected_text_startswith": "[dacscv-eventbridge-implementation-poc|REQ-ae43c9e7]",
        "is_from_me": 1,
    },
    # Untagged self-reply (is_from_me=1, NOT Claude-tagged)
    "untagged_self_reply": {
        "hex": (
            "040b73747265616d747970656481e803840140848484124e534174747269627574"
            "6564537472696e67008484084e534f626a656374008592848484084e5353747269"
            "6e67019484012b81970048657920626162792049206a75737420617272697665"
            "642061742074686520706c616365206f662074686520696e73706563746f722e20"
            "5761732063616c6c696e67206d65207768656e204920776173206c6173742074"
            "616c6b696e6720746f20796f752e20506c65617365206c6574206d65206b6e6f77"
            "20796f75206d616465206974206f6e2074686520706c616e6520736166652e8684"
            "02694901819700928484840c4e5344696374696f6e617279009484016901928496"
            "961d5f5f6b494d4d657373616765506172744174747269627574654e616d658692"
            "848484084e534e756d626572008484074e5356616c7565009484012a8499990086"
            "8686"
        ),
        "expected_text_startswith": "Hey baby I just arrived",
        "is_from_me": 1,
    },
}


def load_query_messages_module():
    """Import query_messages.py as a module from the source directory.

    Uses importlib to load from file path since src/imessage-notify/
    is not a Python package.
    """
    module_path = SKILL_DIR / "query_messages.py"
    spec = importlib.util.spec_from_file_location("query_messages", module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def create_chat_db(db_path, messages, recipient="+13522339160"):
    """Create a minimal chat.db with the given messages.

    Args:
        db_path: Path to create the SQLite database.
        messages: List of dicts with keys: rowid, text, attributed_body_hex,
                  date, is_from_me. attributed_body_hex is optional.
        recipient: The chat_identifier value.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE message (
            ROWID INTEGER PRIMARY KEY,
            text TEXT,
            attributedBody BLOB,
            date INTEGER,
            is_from_me INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE chat (
            ROWID INTEGER PRIMARY KEY,
            chat_identifier TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE chat_message_join (
            chat_id INTEGER,
            message_id INTEGER
        )
    """)
    conn.execute("INSERT INTO chat VALUES (1, ?)", (recipient,))

    for msg in messages:
        blob = bytes.fromhex(msg["attributed_body_hex"]) if msg.get("attributed_body_hex") else None
        conn.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?, ?)",
            (msg["rowid"], msg.get("text"), blob, msg["date"], msg["is_from_me"]),
        )
        conn.execute(
            "INSERT INTO chat_message_join VALUES (1, ?)",
            (msg["rowid"],),
        )

    conn.commit()
    conn.close()


@pytest.fixture()
def chat_db(tmp_path):
    """Create a test chat.db with various message types for attributedBody testing.

    Returns dict with keys: db_path, recipient, apple_ts
    """
    db_path = tmp_path / "chat.db"
    recipient = "+13522339160"
    # apple_ts just before all test messages
    base_date = 800000000000000000

    messages = [
        # 1: Normal text message (text column populated)
        {
            "rowid": 1,
            "text": "Hello from text column",
            "date": base_date + 1,
            "is_from_me": 0,
        },
        # 2: attributedBody only — short user reply "Yes"
        {
            "rowid": 2,
            "attributed_body_hex": TYPEDSTREAM_BLOBS["short_user_reply"]["hex"],
            "date": base_date + 2,
            "is_from_me": 0,
        },
        # 3: attributedBody only — Claude-tagged (should be filtered when is_from_me=1)
        {
            "rowid": 3,
            "attributed_body_hex": TYPEDSTREAM_BLOBS["claude_tagged"]["hex"],
            "date": base_date + 3,
            "is_from_me": 1,
        },
        # 4: attributedBody only — untagged self-reply (should pass filter)
        {
            "rowid": 4,
            "attributed_body_hex": TYPEDSTREAM_BLOBS["untagged_self_reply"]["hex"],
            "date": base_date + 4,
            "is_from_me": 1,
        },
        # 5: Both text and attributedBody (text should win)
        {
            "rowid": 5,
            "text": "Text wins over blob",
            "attributed_body_hex": TYPEDSTREAM_BLOBS["short_user_reply"]["hex"],
            "date": base_date + 5,
            "is_from_me": 0,
        },
        # 6: Neither text nor attributedBody (should be skipped)
        {
            "rowid": 6,
            "date": base_date + 6,
            "is_from_me": 0,
        },
        # 7: attributedBody with leading control chars
        {
            "rowid": 7,
            "attributed_body_hex": TYPEDSTREAM_BLOBS["user_reply_control_chars"]["hex"],
            "date": base_date + 7,
            "is_from_me": 0,
        },
    ]

    create_chat_db(db_path, messages, recipient)

    return {
        "db_path": db_path,
        "recipient": recipient,
        "apple_ts": base_date,
    }
