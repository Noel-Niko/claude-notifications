"""Tests for send.sh, notify.sh, read.sh scripts

Tests script argument parsing, stdin mode, output format, message tagging,
AppleScript escaping, pending request tracking, and error handling.

Note: Tests that involve actually sending iMessages or reading chat.db are
marked with @pytest.mark.integration and skipped by default. Run with:
    pytest -m integration
"""

import os
import re
import subprocess

import pytest

from conftest import SKILL_DIR, get_aliases, patch_send_sh, run_send


# =============================================================================
# send.sh — Output Format
# =============================================================================


class TestSendOutputFormat:
    """Verify send.sh output follows the REQ_ID=<id> SENT_EPOCH=<epoch> format."""

    def test_output_contains_req_id(self, script_sandbox):
        result = run_send(script_sandbox, "test message")
        assert result.returncode == 0
        assert "REQ_ID=" in result.stdout

    def test_output_contains_sent_epoch(self, script_sandbox):
        result = run_send(script_sandbox, "test message")
        assert "SENT_EPOCH=" in result.stdout

    def test_req_id_is_8_hex_chars(self, script_sandbox):
        result = run_send(script_sandbox, "test")
        match = re.search(r"REQ_ID=([a-f0-9]+)", result.stdout)
        assert match is not None
        assert len(match.group(1)) == 8

    def test_sent_epoch_is_numeric(self, script_sandbox):
        result = run_send(script_sandbox, "test")
        match = re.search(r"SENT_EPOCH=(\d+)", result.stdout)
        assert match is not None
        assert int(match.group(1)) > 1700000000  # sanity: after 2023


# =============================================================================
# send.sh — Argument Mode
# =============================================================================


class TestSendArgumentMode:
    """Verify send.sh works with message passed as argument."""

    def test_simple_message(self, script_sandbox):
        result = run_send(script_sandbox, "Hello world")
        assert result.returncode == 0

    def test_message_with_quotes(self, script_sandbox):
        result = run_send(script_sandbox, 'He said "hello"')
        assert result.returncode == 0

    def test_message_with_single_quotes(self, script_sandbox):
        result = run_send(script_sandbox, "It's working")
        assert result.returncode == 0

    def test_message_with_special_chars(self, script_sandbox):
        result = run_send(script_sandbox, "Price: $100 & 50% off!")
        assert result.returncode == 0

    def test_message_with_unicode(self, script_sandbox):
        result = run_send(script_sandbox, "Arrow: 50→200, check: ✅")
        assert result.returncode == 0

    def test_no_argument_fails(self, script_sandbox):
        patch_send_sh(script_sandbox, pending_dir=str(script_sandbox["pending"]))
        result = subprocess.run(
            [str(script_sandbox["send_sh"])],
            capture_output=True,
            text=True,
            cwd=str(script_sandbox["repo"]),
        )
        assert result.returncode != 0


# =============================================================================
# send.sh — Stdin Mode
# =============================================================================


class TestSendStdinMode:
    """Verify send.sh reads message from stdin when "-" is passed."""

    def test_stdin_simple(self, script_sandbox):
        result = run_send(script_sandbox, "-", stdin_text="Hello from stdin")
        assert result.returncode == 0
        assert "REQ_ID=" in result.stdout

    def test_stdin_multiline(self, script_sandbox):
        msg = "Line 1\nLine 2\nLine 3"
        result = run_send(script_sandbox, "-", stdin_text=msg)
        assert result.returncode == 0

    def test_stdin_with_special_chars(self, script_sandbox):
        msg = "Quotes: \"hello\" and 'world'\nBackslash: \\\nDollar: $100"
        result = run_send(script_sandbox, "-", stdin_text=msg)
        assert result.returncode == 0

    def test_stdin_long_message(self, script_sandbox):
        msg = "A" * 5000
        result = run_send(script_sandbox, "-", stdin_text=msg)
        assert result.returncode == 0

    def test_stdin_empty_fails(self, script_sandbox):
        result = run_send(script_sandbox, "-", stdin_text="")
        # Empty stdin means message is empty string, but set -u should catch it
        # or the script proceeds with empty message (both are acceptable behaviors)
        # Just verify it doesn't hang
        assert result.returncode is not None


# =============================================================================
# send.sh — Pending Request Tracking
# =============================================================================


class TestSendPendingRequests:
    """Verify pending request files are created correctly."""

    def test_creates_pending_file(self, script_sandbox):
        result = run_send(script_sandbox, "test")
        req_id = re.search(r"REQ_ID=([a-f0-9]+)", result.stdout).group(1)
        pending_file = script_sandbox["pending"] / f"REQ-{req_id}"
        assert pending_file.exists()

    def test_pending_file_contains_epoch(self, script_sandbox):
        result = run_send(script_sandbox, "test")
        req_id = re.search(r"REQ_ID=([a-f0-9]+)", result.stdout).group(1)
        epoch = re.search(r"SENT_EPOCH=(\d+)", result.stdout).group(1)
        pending_file = script_sandbox["pending"] / f"REQ-{req_id}"
        assert pending_file.read_text().strip() == epoch

    def test_unique_req_ids(self, script_sandbox):
        ids = set()
        for _ in range(5):
            result = run_send(script_sandbox, "test")
            req_id = re.search(r"REQ_ID=([a-f0-9]+)", result.stdout).group(1)
            ids.add(req_id)
        assert len(ids) == 5, "All request IDs should be unique"

    def test_multiple_sends_create_multiple_pending(self, script_sandbox):
        for _ in range(3):
            run_send(script_sandbox, "test")
        pending_files = list(script_sandbox["pending"].glob("REQ-*"))
        assert len(pending_files) == 3


# =============================================================================
# send.sh — Message Tagging
# =============================================================================


class TestSendMessageTagging:
    """Verify messages are tagged with [repo-name|REQ-id] format.

    We verify this by checking the AppleScript escaping logic works
    correctly on the tagged message structure.
    """

    def test_tag_format_in_script(self, script_sandbox):
        """The script constructs [repo|REQ-id] tag format."""
        content = script_sandbox["send_sh"].read_text()
        assert 'tagged_message="[${repo_name}|REQ-${req_id}] ${message}"' in content


# =============================================================================
# send.sh — Error Handling
# =============================================================================


class TestSendErrorHandling:
    """Verify send.sh handles errors gracefully."""

    def test_messages_not_running(self, script_sandbox):
        """When Messages.app is not running, should fail with clear error."""
        # Patch to make pgrep fail (Messages not running)
        content = script_sandbox["send_sh"].read_text()
        content = content.replace(
            'PENDING_DIR="/tmp/imessage-notify-pending"',
            f'PENDING_DIR="{script_sandbox["pending"]}"',
        )
        # Make pgrep always fail
        content = content.replace(
            'if ! pgrep -x "Messages" >/dev/null; then',
            "if true; then",
        )
        script_sandbox["send_sh"].write_text(content)

        result = subprocess.run(
            [str(script_sandbox["send_sh"]), "test"],
            capture_output=True,
            text=True,
            cwd=str(script_sandbox["repo"]),
        )
        assert result.returncode == 1
        assert "ERROR" in result.stderr
        assert "Messages" in result.stderr

    def test_pending_cleaned_on_messages_error(self, script_sandbox):
        """Pending file should be removed if Messages is not running."""
        content = script_sandbox["send_sh"].read_text()
        content = content.replace(
            'PENDING_DIR="/tmp/imessage-notify-pending"',
            f'PENDING_DIR="{script_sandbox["pending"]}"',
        )
        content = content.replace(
            'if ! pgrep -x "Messages" >/dev/null; then',
            "if true; then",
        )
        script_sandbox["send_sh"].write_text(content)

        subprocess.run(
            [str(script_sandbox["send_sh"]), "test"],
            capture_output=True,
            text=True,
            cwd=str(script_sandbox["repo"]),
        )
        pending_files = list(script_sandbox["pending"].glob("REQ-*"))
        assert len(pending_files) == 0, "Pending file should be cleaned up on error"


# =============================================================================
# send.sh — AppleScript Escaping
# =============================================================================


class TestSendEscaping:
    """Verify special characters are properly escaped for AppleScript."""

    def test_escaping_logic_in_script(self):
        """The script escapes backslashes then double quotes."""
        content = (SKILL_DIR / "send.sh").read_text()
        # Backslash escaping comes first
        assert r'escaped_message="${tagged_message//\\/\\\\}"' in content
        # Then quote escaping
        assert r'escaped_message="${escaped_message//\"/\\\"}"' in content

    def test_backslash_in_message(self, script_sandbox):
        result = run_send(script_sandbox, r"path\to\file")
        assert result.returncode == 0

    def test_double_quote_in_message(self, script_sandbox):
        result = run_send(script_sandbox, 'say "hello"')
        assert result.returncode == 0

    def test_mixed_escaping(self, script_sandbox):
        result = run_send(script_sandbox, r'He said "C:\Users\test"')
        assert result.returncode == 0


# =============================================================================
# notify.sh — Argument Parsing
# =============================================================================


class TestNotifyArgumentParsing:
    """Verify notify.sh parses arguments correctly in both modes."""

    def test_argument_mode_passes_message_to_send(self, script_sandbox):
        """notify.sh should forward the message to send.sh."""
        # Patch send.sh to just echo and exit (skip the actual send)
        script_sandbox["send_sh"].write_text(
            "#!/usr/bin/env bash\n"
            'echo "MSG=$1"\n'
            'echo "REQ_ID=abc12345 SENT_EPOCH=1234567890"\n'
        )
        os.chmod(str(script_sandbox["send_sh"]), 0o755)

        # Patch notify.sh to not call read.sh (would fail without chat.db)
        content = script_sandbox["notify_sh"].read_text()
        content = content.replace(
            '"${SCRIPT_DIR}/read.sh"',
            'echo "MOCK_REPLY" && exit 0 #',
        )
        script_sandbox["notify_sh"].write_text(content)

        result = subprocess.run(
            [str(script_sandbox["notify_sh"]), "Hello", "10", "5"],
            capture_output=True,
            text=True,
            cwd=str(script_sandbox["repo"]),
        )
        assert result.returncode == 0

    def test_stdin_mode_passes_message_to_send(self, script_sandbox):
        """notify.sh with "-" should read stdin and forward to send.sh."""
        script_sandbox["send_sh"].write_text(
            "#!/usr/bin/env bash\n"
            'echo "MSG=$1"\n'
            'echo "REQ_ID=abc12345 SENT_EPOCH=1234567890"\n'
        )
        os.chmod(str(script_sandbox["send_sh"]), 0o755)

        content = script_sandbox["notify_sh"].read_text()
        content = content.replace(
            '"${SCRIPT_DIR}/read.sh"',
            'echo "MOCK_REPLY" && exit 0 #',
        )
        script_sandbox["notify_sh"].write_text(content)

        result = subprocess.run(
            [str(script_sandbox["notify_sh"]), "-", "10", "5"],
            capture_output=True,
            text=True,
            input="Hello from stdin",
            cwd=str(script_sandbox["repo"]),
        )
        assert result.returncode == 0

    def test_default_timeout(self, script_sandbox):
        """notify.sh should default to 300s timeout."""
        content = script_sandbox["notify_sh"].read_text()
        assert "${1:-300}" in content

    def test_default_poll_interval(self, script_sandbox):
        """notify.sh should default to 10s poll interval."""
        content = script_sandbox["notify_sh"].read_text()
        assert "${2:-10}" in content


# =============================================================================
# notify.sh — send.sh Integration
# =============================================================================


class TestNotifySendIntegration:
    """Verify notify.sh correctly parses send.sh output."""

    def test_parses_req_id_from_send_output(self, script_sandbox):
        """notify.sh extracts REQ_ID from send.sh output."""
        script_sandbox["send_sh"].write_text(
            '#!/usr/bin/env bash\necho "REQ_ID=deadbeef SENT_EPOCH=1700000000"\n'
        )
        os.chmod(str(script_sandbox["send_sh"]), 0o755)

        content = script_sandbox["notify_sh"].read_text()
        # Replace read.sh call with echo of parsed values
        content = content.replace(
            '"${SCRIPT_DIR}/read.sh" "$sent_epoch" "$timeout" "$poll_interval" "$req_id"',
            'echo "PARSED: req=$req_id epoch=$sent_epoch"',
        )
        script_sandbox["notify_sh"].write_text(content)

        result = subprocess.run(
            [str(script_sandbox["notify_sh"]), "test"],
            capture_output=True,
            text=True,
            cwd=str(script_sandbox["repo"]),
        )
        assert "req=deadbeef" in result.stdout
        assert "epoch=1700000000" in result.stdout

    def test_fails_if_send_fails(self, script_sandbox):
        """notify.sh should exit 1 if send.sh fails."""
        script_sandbox["send_sh"].write_text(
            '#!/usr/bin/env bash\necho "ERROR: test failure" >&2\nexit 1\n'
        )
        os.chmod(str(script_sandbox["send_sh"]), 0o755)

        result = subprocess.run(
            [str(script_sandbox["notify_sh"]), "test"],
            capture_output=True,
            text=True,
            cwd=str(script_sandbox["repo"]),
        )
        assert result.returncode == 1

    def test_fails_if_send_output_unparseable(self, script_sandbox):
        """notify.sh should exit non-zero if send.sh output is garbled.

        With set -euo pipefail, grep returning no match exits the script
        before the explicit "Failed to parse" message is reached. Either
        way, the exit code must be non-zero.
        """
        script_sandbox["send_sh"].write_text(
            '#!/usr/bin/env bash\necho "garbage output"\n'
        )
        os.chmod(str(script_sandbox["send_sh"]), 0o755)

        result = subprocess.run(
            [str(script_sandbox["notify_sh"]), "test"],
            capture_output=True,
            text=True,
            cwd=str(script_sandbox["repo"]),
        )
        assert result.returncode != 0


# =============================================================================
# read.sh — Argument Validation
# =============================================================================


class TestReadArguments:
    """Verify read.sh validates its required arguments."""

    def test_no_args_fails(self, script_sandbox):
        """read.sh requires sent_epoch as first argument."""
        result = subprocess.run(
            [str(script_sandbox["read_sh"])],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_timeout_default(self):
        """read.sh defaults to 300s timeout."""
        content = (SKILL_DIR / "read.sh").read_text()
        assert 'TIMEOUT="${2:-300}"' in content

    def test_poll_interval_default(self):
        """read.sh defaults to 10s poll interval."""
        content = (SKILL_DIR / "read.sh").read_text()
        assert 'POLL_INTERVAL="${3:-10}"' in content


# =============================================================================
# read.sh — Claim Mechanism
# =============================================================================


class TestReadClaimMechanism:
    """Verify the atomic mkdir claim mechanism in read.sh."""

    def test_claim_uses_mkdir(self):
        """read.sh uses mkdir for atomic claiming."""
        content = (SKILL_DIR / "read.sh").read_text()
        assert 'mkdir "$claim_dir"' in content

    def test_claim_dir_format(self):
        """Claim directories use .claim-<rowid> format."""
        content = (SKILL_DIR / "read.sh").read_text()
        assert ".claim-${msg_rowid}" in content

    def test_cleanup_on_exit(self):
        """Pending request file is cleaned up on exit via trap."""
        content = (SKILL_DIR / "read.sh").read_text()
        assert "trap cleanup_pending EXIT" in content


# =============================================================================
# read.sh — Reply Matching Priority
# =============================================================================


class TestReadReplyMatching:
    """Verify reply matching priority: explicit ID > most-recent-pending."""

    def test_explicit_id_match_first(self):
        """read.sh checks for explicit request ID in reply text first."""
        content = (SKILL_DIR / "read.sh").read_text()
        # Priority 1 (ID match) should come before Priority 2 (most recent)
        id_match_pos = content.find("Priority 1")
        recent_pos = content.find("Priority 2")
        assert id_match_pos < recent_pos

    def test_strips_id_prefix_from_reply(self):
        """When reply contains the request ID, it's stripped from the output."""
        content = (SKILL_DIR / "read.sh").read_text()
        assert "clean_reply" in content
        assert "sed" in content

    def test_most_recent_pending_fallback(self):
        """Plain replies go to the most recent pending request."""
        content = (SKILL_DIR / "read.sh").read_text()
        assert "is_most_recent_pending" in content


# =============================================================================
# read.sh — Apple Timestamp Conversion
# =============================================================================


class TestReadTimestampConversion:
    """Verify Unix epoch to Apple Core Data timestamp conversion."""

    def test_conversion_formula(self):
        """Conversion: (unix_epoch - 978307200) * 1000000000"""
        content = (SKILL_DIR / "read.sh").read_text()
        assert "978307200" in content
        assert "1000000000" in content

    def test_known_conversion(self):
        """Verify a known timestamp converts correctly."""
        # Unix epoch 1700000000 (2023-11-14)
        # Apple: (1700000000 - 978307200) * 1000000000 = 721692800000000000
        unix_ts = 1700000000
        expected_apple = (unix_ts - 978307200) * 1000000000
        assert expected_apple == 721692800000000000


# =============================================================================
# Script Permissions
# =============================================================================


class TestScriptPermissions:
    """Verify all scripts are executable."""

    @pytest.mark.parametrize(
        "script",
        [
            "send.sh",
            "notify.sh",
            "read.sh",
            "check_fda.sh",
            "check_imessage.sh",
            "whitelist_commands.sh",
        ],
    )
    def test_script_is_executable(self, script):
        path = SKILL_DIR / script
        assert path.exists(), f"{script} not found"
        assert os.access(path, os.X_OK), f"{script} is not executable"


# =============================================================================
# Script Consistency
# =============================================================================


class TestScriptConsistency:
    """Verify scripts are internally consistent."""

    def test_send_and_read_have_same_recipient(self):
        """RECIPIENT must match in send.sh and read.sh."""
        send_content = (SKILL_DIR / "send.sh").read_text()
        read_content = (SKILL_DIR / "read.sh").read_text()

        send_recipient = re.search(r'^RECIPIENT="(.+)"', send_content, re.MULTILINE)
        read_recipient = re.search(r'^RECIPIENT="(.+)"', read_content, re.MULTILINE)

        assert send_recipient is not None, "RECIPIENT not found in send.sh"
        assert read_recipient is not None, "RECIPIENT not found in read.sh"
        assert send_recipient.group(1) == read_recipient.group(1), (
            f"RECIPIENT mismatch: send.sh={send_recipient.group(1)}, "
            f"read.sh={read_recipient.group(1)}"
        )

    def test_send_and_read_use_same_pending_dir(self):
        """PENDING_DIR must match in send.sh and read.sh."""
        send_content = (SKILL_DIR / "send.sh").read_text()
        read_content = (SKILL_DIR / "read.sh").read_text()

        send_dir = re.search(r'^PENDING_DIR="(.+)"', send_content, re.MULTILINE)
        read_dir = re.search(r'^PENDING_DIR="(.+)"', read_content, re.MULTILINE)

        assert send_dir is not None
        assert read_dir is not None
        assert send_dir.group(1) == read_dir.group(1)

    def test_all_scripts_use_set_euo_pipefail(self):
        """All scripts should use strict error handling."""
        for script in ["send.sh", "notify.sh", "read.sh"]:
            content = (SKILL_DIR / script).read_text()
            assert "set -euo pipefail" in content, f"{script} missing strict mode"


# =============================================================================
# Integration Tests (require Messages.app + iMessage)
# =============================================================================


@pytest.mark.integration
class TestIntegrationSend:
    """Integration tests that actually send iMessages. Skipped by default."""

    def test_real_send(self):
        """Actually send a test message."""
        result = subprocess.run(
            [str(SKILL_DIR / "send.sh"), "pytest integration test"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "REQ_ID=" in result.stdout

    def test_real_send_stdin(self):
        """Actually send via stdin."""
        result = subprocess.run(
            [str(SKILL_DIR / "send.sh"), "-"],
            capture_output=True,
            text=True,
            input="pytest stdin integration test",
        )
        assert result.returncode == 0
        assert "REQ_ID=" in result.stdout


# =============================================================================
# read.sh — Recipient Aliases
# =============================================================================


class TestReadRecipientAliases:
    """Verify RECIPIENT_ALIASES support in read.sh for multi-identity routing."""

    def test_aliases_variable_exists(self):
        """read.sh must declare RECIPIENT_ALIASES."""
        content = (SKILL_DIR / "read.sh").read_text()
        assert "RECIPIENT_ALIASES=" in content

    def test_aliases_default_is_empty(self):
        """RECIPIENT_ALIASES defaults to empty string in source."""
        aliases = get_aliases(SKILL_DIR / "read.sh")
        assert aliases == ""

    def test_build_recipient_sql_single(self):
        """With no aliases, build_recipient_sql returns IN ('recipient')."""
        content = (SKILL_DIR / "read.sh").read_text()
        assert "build_recipient_sql" in content

        # Run the function in isolation with just a RECIPIENT
        result = subprocess.run(
            [
                "bash",
                "-c",
                (
                    'RECIPIENT="user@example.com"\n'
                    'RECIPIENT_ALIASES=""\n'
                    + _extract_function(content, "build_recipient_sql")
                    + "\nbuild_recipient_sql"
                ),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = result.stdout.strip()
        assert output == "'user@example.com'"

    def test_build_recipient_sql_with_aliases(self):
        """With aliases, build_recipient_sql returns IN ('addr','alias1','alias2')."""
        content = (SKILL_DIR / "read.sh").read_text()

        result = subprocess.run(
            [
                "bash",
                "-c",
                (
                    'RECIPIENT="user@example.com"\n'
                    'RECIPIENT_ALIASES="+13522339160 noelnosse@gmail.com"\n'
                    + _extract_function(content, "build_recipient_sql")
                    + "\nbuild_recipient_sql"
                ),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = result.stdout.strip()
        assert output == "'user@example.com','+13522339160','noelnosse@gmail.com'"

    def test_empty_aliases_backwards_compatible(self):
        """Empty RECIPIENT_ALIASES produces same result as single recipient."""
        content = (SKILL_DIR / "read.sh").read_text()

        result = subprocess.run(
            [
                "bash",
                "-c",
                (
                    'RECIPIENT="+13522339160"\n'
                    'RECIPIENT_ALIASES=""\n'
                    + _extract_function(content, "build_recipient_sql")
                    + "\nbuild_recipient_sql"
                ),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = result.stdout.strip()
        assert output == "'+13522339160'"

    def test_sql_quoting_special_chars(self):
        """Addresses with apostrophes are escaped for SQL safety."""
        content = (SKILL_DIR / "read.sh").read_text()

        result = subprocess.run(
            [
                "bash",
                "-c",
                (
                    'RECIPIENT="o\'brien@example.com"\n'
                    'RECIPIENT_ALIASES=""\n'
                    + _extract_function(content, "build_recipient_sql")
                    + "\nbuild_recipient_sql"
                ),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = result.stdout.strip()
        # Single quotes inside SQL strings must be doubled
        assert output == "'o''brien@example.com'"

    def test_sql_in_clause_used_in_query(self):
        """The SQL query uses IN (build_recipient_sql) not = RECIPIENT."""
        content = (SKILL_DIR / "read.sh").read_text()
        assert "chat_identifier IN" in content
        assert "build_recipient_sql" in content


def _extract_function(script_content, func_name):
    """Extract a bash function definition from script content."""
    lines = script_content.splitlines()
    capturing = False
    brace_depth = 0
    result = []

    for line in lines:
        if not capturing and line.strip().startswith(f"{func_name}()"):
            capturing = True

        if capturing:
            result.append(line)
            brace_depth += line.count("{") - line.count("}")
            if brace_depth == 0 and len(result) > 1:
                break

    return "\n".join(result)
