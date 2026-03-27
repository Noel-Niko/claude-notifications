"""Tests for uninstall.sh

Verifies complete cleanup of all artifacts created by install.sh:
skill directory, global permissions (tilde + absolute), CLAUDE.md blocks,
parent .gitignore entry, runtime pending dir, and per-repo local settings.
"""

import json
import shutil

from conftest import (
    EXPECTED_PERMISSIONS,
    IMESSAGE_MARKER,
    POST_COMPACT_MARKER,
    SAMPLE_CLAUDE_MD_INSTALLER_ONLY,
    expected_absolute_permissions,
    read_settings,
    run_uninstall,
)


# =============================================================================
# Skill Directory Removal
# =============================================================================


class TestSkillDirRemoval:
    """Verify ~/.claude/skills/imessage-notify/ is removed."""

    def test_skill_dir_removed(self, uninstall_sandbox):
        assert uninstall_sandbox["skill"].exists()
        run_uninstall(uninstall_sandbox)
        assert not uninstall_sandbox["skill"].exists()

    def test_idempotent_on_missing_dir(self, uninstall_sandbox):
        shutil.rmtree(uninstall_sandbox["skill"])
        run_uninstall(uninstall_sandbox)
        assert not uninstall_sandbox["skill"].exists()


# =============================================================================
# Global Permission Cleanup
# =============================================================================


class TestGlobalPermissionCleanup:
    """Verify tilde + absolute permissions removed from ~/.claude/settings.json."""

    def test_tilde_permissions_removed(self, uninstall_sandbox):
        run_uninstall(uninstall_sandbox)
        settings = read_settings(uninstall_sandbox["global_settings"])
        for perm in EXPECTED_PERMISSIONS:
            assert perm not in settings["permissions"]["allow"]

    def test_absolute_permissions_removed(self, uninstall_sandbox):
        run_uninstall(uninstall_sandbox)
        settings = read_settings(uninstall_sandbox["global_settings"])
        abs_perms = expected_absolute_permissions(str(uninstall_sandbox["home"]))
        for perm in abs_perms:
            assert perm not in settings["permissions"]["allow"]

    def test_other_settings_preserved(self, uninstall_sandbox):
        run_uninstall(uninstall_sandbox)
        settings = read_settings(uninstall_sandbox["global_settings"])
        assert settings["env"]["SOME_VAR"] == "preserved"
        assert "Bash(git status)" in settings["permissions"]["allow"]

    def test_no_permissions_section(self, uninstall_sandbox):
        """Settings file with no permissions key should not cause an error."""
        uninstall_sandbox["global_settings"].write_text(json.dumps({"env": {"A": "B"}}))
        run_uninstall(uninstall_sandbox)


# =============================================================================
# CLAUDE.md Cleanup
# =============================================================================


class TestClaudeMdCleanup:
    """Verify both installer blocks removed from ~/.claude/CLAUDE.md."""

    def test_post_compact_rule_removed(self, uninstall_sandbox):
        run_uninstall(uninstall_sandbox)
        content = uninstall_sandbox["claude_md"].read_text()
        assert POST_COMPACT_MARKER not in content

    def test_imessage_block_removed(self, uninstall_sandbox):
        run_uninstall(uninstall_sandbox)
        content = uninstall_sandbox["claude_md"].read_text()
        assert IMESSAGE_MARKER not in content

    def test_other_content_preserved(self, uninstall_sandbox):
        run_uninstall(uninstall_sandbox)
        content = uninstall_sandbox["claude_md"].read_text()
        assert "## Code Style & Practices" in content
        assert "## Workflow" in content

    def test_empty_file_deleted(self, uninstall_sandbox):
        """CLAUDE.md with only installer blocks should be deleted."""
        uninstall_sandbox["claude_md"].write_text(SAMPLE_CLAUDE_MD_INSTALLER_ONLY)
        run_uninstall(uninstall_sandbox)
        assert not uninstall_sandbox["claude_md"].exists()

    def test_no_claude_md(self, uninstall_sandbox):
        """Missing CLAUDE.md should not cause an error."""
        uninstall_sandbox["claude_md"].unlink()
        run_uninstall(uninstall_sandbox)
        assert not uninstall_sandbox["claude_md"].exists()

    def test_no_trailing_whitespace(self, uninstall_sandbox):
        """Remaining content should not have excessive trailing whitespace."""
        run_uninstall(uninstall_sandbox)
        content = uninstall_sandbox["claude_md"].read_text()
        assert content == content.rstrip() + "\n"


# =============================================================================
# Parent .gitignore Cleanup
# =============================================================================


class TestGitignoreCleanup:
    """Verify parent .gitignore entry removed."""

    def test_entry_removed(self, uninstall_sandbox):
        run_uninstall(uninstall_sandbox)
        content = uninstall_sandbox["parent_gitignore"].read_text()
        assert "claude-notifications/" not in content

    def test_comment_removed(self, uninstall_sandbox):
        run_uninstall(uninstall_sandbox)
        content = uninstall_sandbox["parent_gitignore"].read_text()
        assert "# Claude notifications (cloned installer)" not in content

    def test_other_entries_preserved(self, uninstall_sandbox):
        run_uninstall(uninstall_sandbox)
        content = uninstall_sandbox["parent_gitignore"].read_text()
        assert "node_modules/" in content
        assert "*.pyc" in content

    def test_empty_gitignore_deleted(self, uninstall_sandbox):
        """Gitignore with only notification entry should be deleted."""
        uninstall_sandbox["parent_gitignore"].write_text(
            "# Claude notifications (cloned installer)\nclaude-notifications/\n"
        )
        run_uninstall(uninstall_sandbox)
        assert not uninstall_sandbox["parent_gitignore"].exists()

    def test_no_parent_repo(self, uninstall_sandbox):
        """No parent git repo should not cause an error."""
        shutil.rmtree(uninstall_sandbox["parent_repo"] / ".git")
        run_uninstall(uninstall_sandbox)


# =============================================================================
# Runtime Artifact Cleanup
# =============================================================================


class TestRuntimeCleanup:
    """Verify /tmp/imessage-notify-pending/ (or PENDING_DIR) removed."""

    def test_pending_dir_removed(self, uninstall_sandbox):
        assert uninstall_sandbox["pending"].exists()
        run_uninstall(uninstall_sandbox)
        assert not uninstall_sandbox["pending"].exists()

    def test_missing_pending_dir(self, uninstall_sandbox):
        """Missing pending dir should not cause an error."""
        shutil.rmtree(uninstall_sandbox["pending"])
        run_uninstall(uninstall_sandbox)


# =============================================================================
# Local Settings Note
# =============================================================================


class TestLocalSettingsNote:
    """Verify output includes both tilde and absolute patterns in the note."""

    def test_output_includes_tilde_patterns(self, uninstall_sandbox):
        result = run_uninstall(uninstall_sandbox)
        for perm in EXPECTED_PERMISSIONS:
            assert perm in result.stdout

    def test_output_includes_absolute_patterns(self, uninstall_sandbox):
        result = run_uninstall(uninstall_sandbox)
        home = str(uninstall_sandbox["home"])
        abs_perms = expected_absolute_permissions(home)
        for perm in abs_perms:
            assert perm in result.stdout


# =============================================================================
# --all Flag (Auto-clean Local Settings)
# =============================================================================


class TestAllFlag:
    """Verify --all flag auto-cleans parent repo's local settings."""

    def test_all_cleans_local_tilde_permissions(self, uninstall_sandbox):
        run_uninstall(uninstall_sandbox, "--all")
        settings = read_settings(uninstall_sandbox["local_settings"])
        for perm in EXPECTED_PERMISSIONS:
            assert perm not in settings["permissions"]["allow"]

    def test_all_cleans_local_absolute_permissions(self, uninstall_sandbox):
        run_uninstall(uninstall_sandbox, "--all")
        settings = read_settings(uninstall_sandbox["local_settings"])
        abs_perms = expected_absolute_permissions(str(uninstall_sandbox["home"]))
        for perm in abs_perms:
            assert perm not in settings["permissions"]["allow"]

    def test_all_preserves_other_local_permissions(self, uninstall_sandbox):
        run_uninstall(uninstall_sandbox, "--all")
        settings = read_settings(uninstall_sandbox["local_settings"])
        assert "Bash(npm test)" in settings["permissions"]["allow"]

    def test_default_does_not_clean_local(self, uninstall_sandbox):
        """Without --all, local settings should not be modified."""
        run_uninstall(uninstall_sandbox)
        settings = read_settings(uninstall_sandbox["local_settings"])
        for perm in EXPECTED_PERMISSIONS:
            assert perm in settings["permissions"]["allow"]

    def test_all_no_local_settings_file(self, uninstall_sandbox):
        """--all with no local settings file should not cause an error."""
        uninstall_sandbox["local_settings"].unlink()
        run_uninstall(uninstall_sandbox, "--all")


# =============================================================================
# Idempotency
# =============================================================================


class TestIdempotency:
    """Verify running uninstall twice is safe."""

    def test_double_run_safe(self, uninstall_sandbox):
        run_uninstall(uninstall_sandbox)
        run_uninstall(uninstall_sandbox)

    def test_double_run_with_all(self, uninstall_sandbox):
        run_uninstall(uninstall_sandbox, "--all")
        run_uninstall(uninstall_sandbox, "--all")


# =============================================================================
# Output Messages
# =============================================================================


class TestOutputMessages:
    """Verify stdout confirms what was removed."""

    def test_confirms_skill_dir_removal(self, uninstall_sandbox):
        result = run_uninstall(uninstall_sandbox)
        assert "Removed" in result.stdout
        assert "imessage-notify" in result.stdout

    def test_confirms_permissions_removal(self, uninstall_sandbox):
        result = run_uninstall(uninstall_sandbox)
        assert "permission" in result.stdout.lower()

    def test_confirms_claude_md_cleanup(self, uninstall_sandbox):
        result = run_uninstall(uninstall_sandbox)
        assert "CLAUDE.md" in result.stdout

    def test_confirms_gitignore_cleanup(self, uninstall_sandbox):
        result = run_uninstall(uninstall_sandbox)
        assert "gitignore" in result.stdout.lower()

    def test_confirms_runtime_cleanup(self, uninstall_sandbox):
        result = run_uninstall(uninstall_sandbox)
        assert "pending" in result.stdout.lower() or "runtime" in result.stdout.lower()
