"""Tests for check_imessage.sh

Verifies Messages.app detection, iMessage activation detection via
AppleScript service query, exit codes, and remediation messages.

Unit tests mock all system calls (pgrep, osascript, open). Integration
tests run on the real system and are skipped by default:
    uv run pytest -m integration
"""

import os
import re
import shutil
import subprocess

import pytest

from conftest import SKILL_DIR


# =============================================================================
# Fixtures & Helpers
# =============================================================================


@pytest.fixture()
def check_sandbox(tmp_path):
    """Sandbox for check_imessage.sh tests.

    Copies the script to a temp dir for safe patching.
    """
    skill = tmp_path / "skill"
    skill.mkdir()
    shutil.copy2(SKILL_DIR / "check_imessage.sh", skill / "check_imessage.sh")

    return {
        "skill": skill,
        "script": skill / "check_imessage.sh",
    }


def patch_check_script(
    script_path,
    messages_app_exists=True,
    messages_running=True,
    imessage_service_count="1",
):
    """Patch check_imessage.sh to mock system calls.

    Replaces:
    - Directory check for /System/Applications/Messages.app
    - pgrep for Messages process
    - open -a Messages (no-op)
    - osascript iMessage service count query
    """
    content = script_path.read_text()

    # Mock Messages.app directory check
    if not messages_app_exists:
        content = content.replace(
            '-d "/System/Applications/Messages.app"',
            '-d "/nonexistent/path"',
        )

    # Mock pgrep (Messages running?)
    if messages_running:
        content = content.replace(
            'pgrep -x "Messages" >/dev/null',
            "true",
        )
    else:
        content = content.replace(
            'pgrep -x "Messages" >/dev/null',
            "false",
        )

    # Mock open -a Messages (no-op in tests)
    content = content.replace("open -a Messages", "true")

    # Mock osascript query result
    if imessage_service_count == "QUERY_FAILED":
        content = re.sub(
            r"osascript -e '.*?' 2>/dev/null",
            "false",
            content,
        )
    else:
        content = re.sub(
            r"osascript -e '.*?' 2>/dev/null",
            f'echo "{imessage_service_count}"',
            content,
        )

    script_path.write_text(content)
    return script_path


def run_check(script_path):
    """Run check_imessage.sh and return the CompletedProcess."""
    return subprocess.run(
        [str(script_path)],
        capture_output=True,
        text=True,
    )


# =============================================================================
# Messages.app Detection
# =============================================================================


class TestMessagesAppDetection:
    """Verify Messages.app existence check at /System/Applications/."""

    def test_messages_app_found(self, check_sandbox):
        patch_check_script(check_sandbox["script"], messages_app_exists=True)
        result = run_check(check_sandbox["script"])
        assert result.returncode == 0

    def test_messages_app_missing_exits_1(self, check_sandbox):
        patch_check_script(
            check_sandbox["script"],
            messages_app_exists=False,
        )
        result = run_check(check_sandbox["script"])
        assert result.returncode == 1

    def test_messages_app_missing_shows_error(self, check_sandbox):
        patch_check_script(
            check_sandbox["script"],
            messages_app_exists=False,
        )
        result = run_check(check_sandbox["script"])
        assert "ERROR" in result.stderr
        assert "Messages.app" in result.stderr

    def test_messages_app_missing_mentions_reinstall(self, check_sandbox):
        patch_check_script(
            check_sandbox["script"],
            messages_app_exists=False,
        )
        result = run_check(check_sandbox["script"])
        assert "macOS" in result.stderr


# =============================================================================
# iMessage Activation — AppleScript Query
# =============================================================================


class TestImessageActivation:
    """Verify iMessage detection via AppleScript service count query."""

    def test_one_imessage_service_returns_0(self, check_sandbox):
        patch_check_script(
            check_sandbox["script"],
            imessage_service_count="1",
        )
        result = run_check(check_sandbox["script"])
        assert result.returncode == 0

    def test_multiple_services_returns_0(self, check_sandbox):
        patch_check_script(
            check_sandbox["script"],
            imessage_service_count="3",
        )
        result = run_check(check_sandbox["script"])
        assert result.returncode == 0

    def test_zero_services_returns_2(self, check_sandbox):
        patch_check_script(
            check_sandbox["script"],
            imessage_service_count="0",
        )
        result = run_check(check_sandbox["script"])
        assert result.returncode == 2

    def test_zero_services_shows_warning(self, check_sandbox):
        patch_check_script(
            check_sandbox["script"],
            imessage_service_count="0",
        )
        result = run_check(check_sandbox["script"])
        assert "WARNING" in result.stderr or "iMessage" in result.stderr

    def test_query_failed_returns_2(self, check_sandbox):
        patch_check_script(
            check_sandbox["script"],
            imessage_service_count="QUERY_FAILED",
        )
        result = run_check(check_sandbox["script"])
        assert result.returncode == 2


# =============================================================================
# Messages Not Running — Launch Behavior
# =============================================================================


class TestMessagesLaunch:
    """Verify behavior when Messages.app is not running."""

    def test_messages_not_running_still_checks_imessage(self, check_sandbox):
        """When Messages isn't running, script launches it and proceeds."""
        patch_check_script(
            check_sandbox["script"],
            messages_running=False,
            imessage_service_count="1",
        )
        result = run_check(check_sandbox["script"])
        assert result.returncode == 0

    def test_messages_not_running_zero_services_returns_2(self, check_sandbox):
        patch_check_script(
            check_sandbox["script"],
            messages_running=False,
            imessage_service_count="0",
        )
        result = run_check(check_sandbox["script"])
        assert result.returncode == 2


# =============================================================================
# Exit Codes
# =============================================================================


class TestExitCodes:
    """Verify distinct exit codes for each failure mode."""

    def test_success_is_0(self, check_sandbox):
        patch_check_script(check_sandbox["script"])
        result = run_check(check_sandbox["script"])
        assert result.returncode == 0

    def test_messages_missing_is_1(self, check_sandbox):
        patch_check_script(
            check_sandbox["script"],
            messages_app_exists=False,
        )
        result = run_check(check_sandbox["script"])
        assert result.returncode == 1

    def test_not_activated_is_2(self, check_sandbox):
        patch_check_script(
            check_sandbox["script"],
            imessage_service_count="0",
        )
        result = run_check(check_sandbox["script"])
        assert result.returncode == 2

    def test_query_failed_is_2(self, check_sandbox):
        patch_check_script(
            check_sandbox["script"],
            imessage_service_count="QUERY_FAILED",
        )
        result = run_check(check_sandbox["script"])
        assert result.returncode == 2


# =============================================================================
# Remediation Instructions
# =============================================================================


class TestRemediationInstructions:
    """Verify failure messages include actionable remediation steps."""

    def test_not_activated_mentions_settings(self, check_sandbox):
        patch_check_script(
            check_sandbox["script"],
            imessage_service_count="0",
        )
        result = run_check(check_sandbox["script"])
        assert "Settings" in result.stderr or "settings" in result.stderr

    def test_not_activated_mentions_apple_id(self, check_sandbox):
        patch_check_script(
            check_sandbox["script"],
            imessage_service_count="0",
        )
        result = run_check(check_sandbox["script"])
        assert "Apple ID" in result.stderr

    def test_not_activated_mentions_sign_in(self, check_sandbox):
        patch_check_script(
            check_sandbox["script"],
            imessage_service_count="0",
        )
        result = run_check(check_sandbox["script"])
        assert "Sign in" in result.stderr or "sign in" in result.stderr

    def test_messages_missing_mentions_paths(self, check_sandbox):
        patch_check_script(
            check_sandbox["script"],
            messages_app_exists=False,
        )
        result = run_check(check_sandbox["script"])
        assert "/System/Applications/Messages.app" in result.stderr


# =============================================================================
# Script Properties
# =============================================================================


class TestScriptProperties:
    """Verify script follows project conventions."""

    def test_is_executable(self):
        path = SKILL_DIR / "check_imessage.sh"
        assert path.exists(), "check_imessage.sh not found"
        assert os.access(path, os.X_OK), "check_imessage.sh is not executable"

    def test_uses_strict_mode(self):
        content = (SKILL_DIR / "check_imessage.sh").read_text()
        assert "set -euo pipefail" in content

    def test_supports_sourcing(self):
        """Script uses BASH_SOURCE pattern for source/execute duality."""
        content = (SKILL_DIR / "check_imessage.sh").read_text()
        assert "BASH_SOURCE[0]" in content

    def test_defines_check_imessage_function(self):
        content = (SKILL_DIR / "check_imessage.sh").read_text()
        assert "check_imessage()" in content


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.integration
class TestIntegrationCheckImessage:
    """Integration tests that run on the real system. Skipped by default."""

    def test_real_check(self):
        """On a configured Mac, should return 0 or 2 (never 1)."""
        result = subprocess.run(
            [str(SKILL_DIR / "check_imessage.sh")],
            capture_output=True,
            text=True,
        )
        assert result.returncode in (0, 2), (
            f"Unexpected exit code {result.returncode}: {result.stderr}"
        )
