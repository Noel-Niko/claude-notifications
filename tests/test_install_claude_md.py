"""Tests for install.sh Step 11: ~/.claude/CLAUDE.md injection.

Covers both 11a (post-compact rule prepend) and 11b (iMessage block append).
Runs the Step 11 bash logic in isolation with a fake $HOME.
"""

import os
import subprocess
from pathlib import Path

import pytest

# ── Constants matching install.sh exactly ──

POST_COMPACT_MARKER = "CRITICAL — POST-COMPACT RULE"

POST_COMPACT_BLOCK = (
    "> **CRITICAL — POST-COMPACT RULE:** After every `/compact`, you MUST"
    " re-read this file (`~/.claude/CLAUDE.md`) in full using the Read tool"
    " **before** doing anything else. Do not rely on the compacted summary"
    " for these rules — the summary may omit or simplify critical constraints."
    " Re-reading ensures no instructions are lost. This rule itself must be"
    " preserved in the compact summary so it triggers the re-read."
)

IMESSAGE_MARKER = "## iMessage Notifications (MANDATORY)"

# ── Extract Step 11 bash snippet from install.sh ──

_INSTALL_SH = Path(__file__).parent.parent / "install.sh"


def _extract_step11_snippet() -> str:
    """Extract Step 11 bash logic from install.sh as a standalone script.

    Reads between the Step 11 comment and the 'Installation complete' banner.
    Wraps in set -euo pipefail and returns a runnable bash string.
    """
    lines = _INSTALL_SH.read_text().splitlines()

    start = None
    end = None
    for i, line in enumerate(lines):
        if "# ─── Step 11: Update ~/.claude/CLAUDE.md ───" in line:
            start = i
        if start is not None and "Installation complete" in line:
            end = i
            break

    assert start is not None, "Could not find Step 11 start marker in install.sh"
    assert end is not None, "Could not find end marker after Step 11 in install.sh"

    snippet = "\n".join(lines[start:end])
    return f"#!/usr/bin/env bash\nset -euo pipefail\n{snippet}"


STEP11_SNIPPET = _extract_step11_snippet()


# ── Fixture ──


@pytest.fixture()
def claude_md_sandbox(tmp_path):
    """Fake $HOME with .claude/ directory for testing CLAUDE.md injection.

    Returns dict with keys: home, claude_md
    """
    home = tmp_path / "home"
    home.mkdir()
    claude_dir = home / ".claude"
    claude_dir.mkdir()
    claude_md = claude_dir / "CLAUDE.md"
    return {"home": home, "claude_md": claude_md}


# ── Helper ──


def run_step11(sandbox, expect_fail=False):
    """Run the extracted Step 11 snippet with the sandbox HOME."""
    result = subprocess.run(
        ["bash", "-c", STEP11_SNIPPET],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(sandbox["home"])},
    )
    if not expect_fail:
        assert result.returncode == 0, (
            f"Step 11 failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


# =============================================================================
# Tests — Step 11a: Post-compact rule
# =============================================================================


class TestPostCompactFreshInstall:
    """Post-compact rule on a fresh install (no existing CLAUDE.md)."""

    def test_creates_claude_md(self, claude_md_sandbox):
        # Remove the .claude dir so mkdir -p is exercised
        claude_md_sandbox["claude_md"].parent.rmdir()
        run_step11(claude_md_sandbox)
        assert claude_md_sandbox["claude_md"].exists()

    def test_contains_post_compact_rule(self, claude_md_sandbox):
        run_step11(claude_md_sandbox)
        content = claude_md_sandbox["claude_md"].read_text()
        assert POST_COMPACT_MARKER in content

    def test_post_compact_is_first_line(self, claude_md_sandbox):
        run_step11(claude_md_sandbox)
        first_line = claude_md_sandbox["claude_md"].read_text().splitlines()[0]
        assert POST_COMPACT_MARKER in first_line


class TestPostCompactPrepend:
    """Post-compact rule prepended to existing content."""

    def test_prepends_before_existing_content(self, claude_md_sandbox):
        claude_md_sandbox["claude_md"].write_text("# Existing header\nSome content\n")
        run_step11(claude_md_sandbox)
        content = claude_md_sandbox["claude_md"].read_text()
        compact_pos = content.index(POST_COMPACT_MARKER)
        existing_pos = content.index("# Existing header")
        assert compact_pos < existing_pos

    def test_preserves_existing_content(self, claude_md_sandbox):
        original = "# My Config\n\nSome important rules here.\n"
        claude_md_sandbox["claude_md"].write_text(original)
        run_step11(claude_md_sandbox)
        content = claude_md_sandbox["claude_md"].read_text()
        assert "# My Config" in content
        assert "Some important rules here." in content

    def test_blank_line_separates_rule_from_existing(self, claude_md_sandbox):
        claude_md_sandbox["claude_md"].write_text("# Existing\n")
        run_step11(claude_md_sandbox)
        content = claude_md_sandbox["claude_md"].read_text()
        # The post-compact block should end with \n\n before existing content
        lines = content.splitlines()
        # Find the blank line between the rule and existing content
        rule_line_idx = next(
            i for i, line in enumerate(lines) if POST_COMPACT_MARKER in line
        )
        # There should be a blank line after the rule before existing content
        assert lines[rule_line_idx + 1] == ""


class TestPostCompactIdempotent:
    """Post-compact rule is not duplicated on repeated runs."""

    def test_skips_if_already_present(self, claude_md_sandbox):
        run_step11(claude_md_sandbox)
        content_after_first = claude_md_sandbox["claude_md"].read_text()
        result = run_step11(claude_md_sandbox)
        content_after_second = claude_md_sandbox["claude_md"].read_text()
        assert content_after_first == content_after_second
        assert "already contains post-compact rule" in result.stdout

    def test_single_occurrence(self, claude_md_sandbox):
        run_step11(claude_md_sandbox)
        run_step11(claude_md_sandbox)
        content = claude_md_sandbox["claude_md"].read_text()
        assert content.count(POST_COMPACT_MARKER) == 1


# =============================================================================
# Tests — Step 11b: iMessage Notifications block
# =============================================================================


class TestIMessageBlockFreshInstall:
    """iMessage block on a fresh install."""

    def test_contains_imessage_block(self, claude_md_sandbox):
        run_step11(claude_md_sandbox)
        content = claude_md_sandbox["claude_md"].read_text()
        assert IMESSAGE_MARKER in content

    def test_contains_phone_mode_instructions(self, claude_md_sandbox):
        run_step11(claude_md_sandbox)
        content = claude_md_sandbox["claude_md"].read_text()
        assert "Phone mode" in content
        assert "notify.sh" in content
        assert "send.sh" in content


class TestIMessageBlockAppend:
    """iMessage block appended to existing content."""

    def test_appends_after_existing(self, claude_md_sandbox):
        claude_md_sandbox["claude_md"].write_text("# Existing\n")
        run_step11(claude_md_sandbox)
        content = claude_md_sandbox["claude_md"].read_text()
        existing_pos = content.index("# Existing")
        imessage_pos = content.index(IMESSAGE_MARKER)
        assert existing_pos < imessage_pos


class TestIMessageBlockIdempotent:
    """iMessage block is not duplicated on repeated runs."""

    def test_updates_if_already_present(self, claude_md_sandbox):
        run_step11(claude_md_sandbox)
        result = run_step11(claude_md_sandbox)
        assert "iMessage Notifications block updated" in result.stdout

    def test_single_occurrence(self, claude_md_sandbox):
        run_step11(claude_md_sandbox)
        run_step11(claude_md_sandbox)
        content = claude_md_sandbox["claude_md"].read_text()
        assert content.count(IMESSAGE_MARKER) == 1


# =============================================================================
# Tests — Combined behavior
# =============================================================================


class TestCombinedBlocks:
    """Both blocks interact correctly."""

    def test_post_compact_before_imessage(self, claude_md_sandbox):
        run_step11(claude_md_sandbox)
        content = claude_md_sandbox["claude_md"].read_text()
        compact_pos = content.index(POST_COMPACT_MARKER)
        imessage_pos = content.index(IMESSAGE_MARKER)
        assert compact_pos < imessage_pos

    def test_fresh_install_has_both(self, claude_md_sandbox):
        run_step11(claude_md_sandbox)
        content = claude_md_sandbox["claude_md"].read_text()
        assert POST_COMPACT_MARKER in content
        assert IMESSAGE_MARKER in content

    def test_existing_content_preserved_between_blocks(self, claude_md_sandbox):
        original = "# My Rules\n\nDo not delete this.\n"
        claude_md_sandbox["claude_md"].write_text(original)
        run_step11(claude_md_sandbox)
        content = claude_md_sandbox["claude_md"].read_text()
        assert "# My Rules" in content
        assert "Do not delete this." in content

    def test_order_post_compact_then_existing_then_imessage(self, claude_md_sandbox):
        claude_md_sandbox["claude_md"].write_text("# Middle Content\n")
        run_step11(claude_md_sandbox)
        content = claude_md_sandbox["claude_md"].read_text()
        compact_pos = content.index(POST_COMPACT_MARKER)
        middle_pos = content.index("# Middle Content")
        imessage_pos = content.index(IMESSAGE_MARKER)
        assert compact_pos < middle_pos < imessage_pos

    def test_full_idempotent_two_runs(self, claude_md_sandbox):
        run_step11(claude_md_sandbox)
        content_first = claude_md_sandbox["claude_md"].read_text()
        run_step11(claude_md_sandbox)
        content_second = claude_md_sandbox["claude_md"].read_text()
        assert content_first == content_second


class TestPartialExisting:
    """Only one block pre-exists — the other is added."""

    def test_has_imessage_adds_post_compact(self, claude_md_sandbox):
        claude_md_sandbox["claude_md"].write_text(
            f"{IMESSAGE_MARKER}\n\nSome iMessage content.\n"
        )
        run_step11(claude_md_sandbox)
        content = claude_md_sandbox["claude_md"].read_text()
        assert POST_COMPACT_MARKER in content
        # Post-compact should still be first
        assert content.index(POST_COMPACT_MARKER) < content.index(IMESSAGE_MARKER)

    def test_has_post_compact_adds_imessage(self, claude_md_sandbox):
        claude_md_sandbox["claude_md"].write_text(f"{POST_COMPACT_BLOCK}\n")
        run_step11(claude_md_sandbox)
        content = claude_md_sandbox["claude_md"].read_text()
        assert IMESSAGE_MARKER in content
        assert content.count(POST_COMPACT_MARKER) == 1


class TestOutputMessages:
    """Stdout messages reflect what was done."""

    def test_fresh_install_messages(self, claude_md_sandbox):
        result = run_step11(claude_md_sandbox)
        assert "Post-compact rule prepended" in result.stdout
        assert "iMessage Notifications block added" in result.stdout

    def test_idempotent_messages(self, claude_md_sandbox):
        run_step11(claude_md_sandbox)
        result = run_step11(claude_md_sandbox)
        assert "already contains post-compact rule" in result.stdout
        assert "iMessage Notifications block updated" in result.stdout
