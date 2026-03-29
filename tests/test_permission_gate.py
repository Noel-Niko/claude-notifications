"""Tests for permission_gate.sh — Claude Code PermissionRequest hook.

Tests the hook script that routes IDE permission prompts through iMessage
when phone mode is active. Written TDD-style.

Run with: uv run pytest tests/test_permission_gate.py -m "not integration"
"""

import json
import os
import subprocess
import time

import pytest

from conftest import run_permission_gate

# ---------------------------------------------------------------------------
# Sample stdin payloads (matching Claude Code's PermissionRequest format)
# ---------------------------------------------------------------------------

WRITE_INPUT = {
    "session_id": "test-session",
    "hook_event_name": "PermissionRequest",
    "tool_name": "Write",
    "tool_input": {"file_path": "/foo/bar.py", "content": "print('hello')"},
    "cwd": "/test/project",
}

BASH_INPUT = {
    "session_id": "test-session",
    "hook_event_name": "PermissionRequest",
    "tool_name": "Bash",
    "tool_input": {"command": "git push origin main"},
    "cwd": "/test/project",
}

EDIT_INPUT = {
    "session_id": "test-session",
    "hook_event_name": "PermissionRequest",
    "tool_name": "Edit",
    "tool_input": {
        "file_path": "/foo/bar.py",
        "old_string": "old",
        "new_string": "new",
    },
    "cwd": "/test/project",
}

READ_INPUT = {
    "session_id": "test-session",
    "hook_event_name": "PermissionRequest",
    "tool_name": "Read",
    "tool_input": {"file_path": "/foo/secrets.env"},
    "cwd": "/test/project",
}

UNKNOWN_INPUT = {
    "session_id": "test-session",
    "hook_event_name": "PermissionRequest",
    "tool_name": "WebFetch",
    "tool_input": {"url": "https://example.com"},
    "cwd": "/test/project",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_decision(result):
    """Parse the JSON decision from hook stdout."""
    output = json.loads(result.stdout)
    return output["hookSpecificOutput"]["decision"]["behavior"]


# ---------------------------------------------------------------------------
# Tests: Phone mode flag detection
# ---------------------------------------------------------------------------


class TestPhoneModeFlag:
    """Tests for phone mode flag file detection."""

    def test_no_phone_mode_flag(self, permission_gate_sandbox):
        """No flag file → exit 0, empty stdout (fall through to IDE prompt)."""
        result = run_permission_gate(permission_gate_sandbox, WRITE_INPUT, reply="yes")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_phone_mode_flag_present(self, permission_gate_sandbox):
        """Flag file exists → hook routes through iMessage and returns decision."""
        permission_gate_sandbox["flag_file"].touch()
        result = run_permission_gate(permission_gate_sandbox, WRITE_INPUT, reply="yes")
        assert result.returncode == 0
        assert _parse_decision(result) == "allow"

    def test_stale_flag_expired(self, permission_gate_sandbox):
        """Flag file older than 4 hours → treated as no phone mode, flag deleted."""
        flag = permission_gate_sandbox["flag_file"]
        flag.touch()
        # Set modification time to 5 hours ago
        stale_time = time.time() - (5 * 3600)
        os.utime(str(flag), (stale_time, stale_time))

        result = run_permission_gate(permission_gate_sandbox, WRITE_INPUT, reply="yes")
        assert result.returncode == 0
        assert result.stdout.strip() == ""
        # Flag should be deleted
        assert not flag.exists()

    def test_fresh_flag_not_expired(self, permission_gate_sandbox):
        """Flag file created recently → routes through iMessage normally."""
        permission_gate_sandbox["flag_file"].touch()
        result = run_permission_gate(permission_gate_sandbox, WRITE_INPUT, reply="yes")
        assert result.returncode == 0
        assert _parse_decision(result) == "allow"


# ---------------------------------------------------------------------------
# Tests: Reply parsing
# ---------------------------------------------------------------------------


class TestReplyParsing:
    """Tests for parsing notify.sh reply text."""

    def test_yes_reply(self, permission_gate_sandbox):
        """Reply 'yes' → allow."""
        permission_gate_sandbox["flag_file"].touch()
        result = run_permission_gate(permission_gate_sandbox, WRITE_INPUT, reply="yes")
        assert result.returncode == 0
        assert _parse_decision(result) == "allow"

    def test_no_reply(self, permission_gate_sandbox):
        """Reply 'no' → deny."""
        permission_gate_sandbox["flag_file"].touch()
        result = run_permission_gate(permission_gate_sandbox, WRITE_INPUT, reply="no")
        assert result.returncode == 0
        assert _parse_decision(result) == "deny"

    @pytest.mark.parametrize("reply", ["YES", "Yes", "y", "Y"])
    def test_case_insensitive_yes(self, permission_gate_sandbox, reply):
        """Various forms of 'yes' all result in allow."""
        permission_gate_sandbox["flag_file"].touch()
        result = run_permission_gate(permission_gate_sandbox, WRITE_INPUT, reply=reply)
        assert result.returncode == 0
        assert _parse_decision(result) == "allow"

    @pytest.mark.parametrize("reply", ["NO", "No", "n", "N"])
    def test_case_insensitive_no(self, permission_gate_sandbox, reply):
        """Various forms of 'no' all result in deny."""
        permission_gate_sandbox["flag_file"].touch()
        result = run_permission_gate(permission_gate_sandbox, WRITE_INPUT, reply=reply)
        assert result.returncode == 0
        assert _parse_decision(result) == "deny"

    def test_ambiguous_reply_denied(self, permission_gate_sandbox):
        """Ambiguous reply (not yes/no) → deny."""
        permission_gate_sandbox["flag_file"].touch()
        result = run_permission_gate(
            permission_gate_sandbox, WRITE_INPUT, reply="maybe"
        )
        assert result.returncode == 0
        assert _parse_decision(result) == "deny"


# ---------------------------------------------------------------------------
# Tests: Timeout and error handling
# ---------------------------------------------------------------------------


class TestTimeoutAndErrors:
    """Tests for timeout and error handling."""

    def test_notify_timeout(self, permission_gate_sandbox):
        """notify.sh timeout → exit 2 with stderr feedback."""
        permission_gate_sandbox["flag_file"].touch()
        result = run_permission_gate(
            permission_gate_sandbox, WRITE_INPUT, reply="timeout"
        )
        assert result.returncode == 2
        assert "no reply" in result.stderr.lower() or "timeout" in result.stderr.lower()

    def test_notify_failure_fallthrough(self, permission_gate_sandbox):
        """notify.sh send failure → exit 0, empty stdout (fall through to IDE)."""
        permission_gate_sandbox["flag_file"].touch()
        result = run_permission_gate(permission_gate_sandbox, WRITE_INPUT, reply="fail")
        assert result.returncode == 0
        assert result.stdout.strip() == ""


# ---------------------------------------------------------------------------
# Tests: Message formatting by tool type
# ---------------------------------------------------------------------------


class TestMessageFormatting:
    """Tests for iMessage formatting by tool type."""

    def test_format_write_tool(self, permission_gate_sandbox):
        """Write tool message includes file path and content length."""
        permission_gate_sandbox["flag_file"].touch()
        run_permission_gate(permission_gate_sandbox, WRITE_INPUT, reply="yes")
        captured = permission_gate_sandbox["capture_file"].read_text()
        assert "Write" in captured
        assert "/foo/bar.py" in captured

    def test_format_write_includes_reply_prompt(self, permission_gate_sandbox):
        """Write tool message asks for YES or NO reply."""
        permission_gate_sandbox["flag_file"].touch()
        run_permission_gate(permission_gate_sandbox, WRITE_INPUT, reply="yes")
        captured = permission_gate_sandbox["capture_file"].read_text()
        assert "YES" in captured
        assert "NO" in captured

    def test_format_bash_tool(self, permission_gate_sandbox):
        """Bash tool message includes the command."""
        permission_gate_sandbox["flag_file"].touch()
        run_permission_gate(permission_gate_sandbox, BASH_INPUT, reply="yes")
        captured = permission_gate_sandbox["capture_file"].read_text()
        assert "git push origin main" in captured

    def test_format_edit_tool(self, permission_gate_sandbox):
        """Edit tool message includes file path."""
        permission_gate_sandbox["flag_file"].touch()
        run_permission_gate(permission_gate_sandbox, EDIT_INPUT, reply="yes")
        captured = permission_gate_sandbox["capture_file"].read_text()
        assert "Edit" in captured
        assert "/foo/bar.py" in captured

    def test_format_read_tool(self, permission_gate_sandbox):
        """Read tool message includes file path."""
        permission_gate_sandbox["flag_file"].touch()
        run_permission_gate(permission_gate_sandbox, READ_INPUT, reply="yes")
        captured = permission_gate_sandbox["capture_file"].read_text()
        assert "Read" in captured
        assert "/foo/secrets.env" in captured

    def test_format_unknown_tool(self, permission_gate_sandbox):
        """Unknown tool shows tool name."""
        permission_gate_sandbox["flag_file"].touch()
        run_permission_gate(permission_gate_sandbox, UNKNOWN_INPUT, reply="yes")
        captured = permission_gate_sandbox["capture_file"].read_text()
        assert "WebFetch" in captured


# ---------------------------------------------------------------------------
# Tests: stdin parsing
# ---------------------------------------------------------------------------


class TestStdinParsing:
    """Tests for JSON stdin parsing."""

    def test_valid_json_parsed(self, permission_gate_sandbox):
        """Valid JSON stdin is parsed correctly into a formatted message."""
        permission_gate_sandbox["flag_file"].touch()
        result = run_permission_gate(permission_gate_sandbox, WRITE_INPUT, reply="yes")
        assert result.returncode == 0
        captured = permission_gate_sandbox["capture_file"].read_text()
        assert "Write" in captured

    def test_empty_stdin_fallthrough(self, permission_gate_sandbox):
        """Empty stdin with phone mode active → graceful fallthrough (exit 0)."""
        permission_gate_sandbox["flag_file"].touch()
        env = {
            **os.environ,
            "PHONE_MODE_FLAG": str(permission_gate_sandbox["flag_file"]),
            "MOCK_NOTIFY_REPLY": "yes",
            "MOCK_NOTIFY_CAPTURE": str(permission_gate_sandbox["capture_file"]),
        }
        result = subprocess.run(
            [str(permission_gate_sandbox["gate_sh"])],
            capture_output=True,
            text=True,
            input="",
            env=env,
        )
        # Should not crash — graceful fallthrough to IDE
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_invalid_json_fallthrough(self, permission_gate_sandbox):
        """Invalid JSON stdin → graceful fallthrough (exit 0)."""
        permission_gate_sandbox["flag_file"].touch()
        env = {
            **os.environ,
            "PHONE_MODE_FLAG": str(permission_gate_sandbox["flag_file"]),
            "MOCK_NOTIFY_REPLY": "yes",
            "MOCK_NOTIFY_CAPTURE": str(permission_gate_sandbox["capture_file"]),
        }
        result = subprocess.run(
            [str(permission_gate_sandbox["gate_sh"])],
            capture_output=True,
            text=True,
            input="not valid json{{{",
            env=env,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""
