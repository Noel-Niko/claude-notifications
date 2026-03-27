"""Tests for whitelist_commands.sh

Verifies phone number normalization, permission injection, RECIPIENT
configuration, idempotency, and edge cases.
"""

import json


from conftest import (
    EXPECTED_PERMISSIONS,
    expected_absolute_permissions,
    get_aliases,
    get_recipient,
    read_settings,
    run_whitelist,
)


# =============================================================================
# Phone Number Normalization
# =============================================================================


class TestPhoneNormalization:
    """Verify phone numbers in various formats are normalized to +1XXXXXXXXXX."""

    def test_plus_country_code(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "+13522339160")
        assert get_recipient(whitelist_sandbox["send_sh"]) == "+13522339160"
        assert get_recipient(whitelist_sandbox["read_sh"]) == "+13522339160"

    def test_dashes_with_country_code(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "1-352-233-9160")
        assert get_recipient(whitelist_sandbox["send_sh"]) == "+13522339160"

    def test_dashes_without_country_code(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "352-233-9160")
        assert get_recipient(whitelist_sandbox["send_sh"]) == "+13522339160"

    def test_parens_format(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "(352) 233-9160")
        assert get_recipient(whitelist_sandbox["send_sh"]) == "+13522339160"

    def test_digits_only_10(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "3522339160")
        assert get_recipient(whitelist_sandbox["send_sh"]) == "+13522339160"

    def test_digits_only_11(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "13522339160")
        assert get_recipient(whitelist_sandbox["send_sh"]) == "+13522339160"

    def test_dots_format(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "352.233.9160")
        assert get_recipient(whitelist_sandbox["send_sh"]) == "+13522339160"

    def test_spaces_format(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "352 233 9160")
        assert get_recipient(whitelist_sandbox["send_sh"]) == "+13522339160"


class TestPhoneNormalizationErrors:
    """Verify invalid phone numbers are rejected."""

    def test_too_few_digits(self, whitelist_sandbox):
        result = run_whitelist(whitelist_sandbox, "123", expect_fail=True)
        assert result.returncode == 1
        assert "ERROR" in result.stderr

    def test_too_many_digits(self, whitelist_sandbox):
        result = run_whitelist(whitelist_sandbox, "123456789012345", expect_fail=True)
        assert result.returncode == 1
        assert "ERROR" in result.stderr

    def test_letters_only(self, whitelist_sandbox):
        result = run_whitelist(whitelist_sandbox, "abcdefghij", expect_fail=True)
        assert result.returncode == 1
        assert "ERROR" in result.stderr


# =============================================================================
# Email Configuration
# =============================================================================


class TestEmailConfiguration:
    """Verify email addresses are passed through as-is."""

    def test_email_recipient(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "user@example.com")
        assert get_recipient(whitelist_sandbox["send_sh"]) == "user@example.com"
        assert get_recipient(whitelist_sandbox["read_sh"]) == "user@example.com"

    def test_icloud_email(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "john.doe@icloud.com")
        assert get_recipient(whitelist_sandbox["send_sh"]) == "john.doe@icloud.com"

    def test_edu_email(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "nnosse@wgu.edu")
        assert get_recipient(whitelist_sandbox["send_sh"]) == "nnosse@wgu.edu"


# =============================================================================
# Permission Injection
# =============================================================================


class TestPermissionInjection:
    """Verify permission entries are injected into settings files."""

    def test_creates_local_settings_from_scratch(self, whitelist_sandbox):
        assert not whitelist_sandbox["local_settings"].exists()
        run_whitelist(whitelist_sandbox)
        assert whitelist_sandbox["local_settings"].exists()
        settings = read_settings(whitelist_sandbox["local_settings"])
        for perm in EXPECTED_PERMISSIONS:
            assert perm in settings["permissions"]["allow"]

    def test_creates_global_settings_from_scratch(self, whitelist_sandbox):
        assert not whitelist_sandbox["global_settings"].exists()
        run_whitelist(whitelist_sandbox)
        assert whitelist_sandbox["global_settings"].exists()
        settings = read_settings(whitelist_sandbox["global_settings"])
        for perm in EXPECTED_PERMISSIONS:
            assert perm in settings["permissions"]["allow"]

    def test_preserves_existing_local_permissions(self, whitelist_sandbox):
        whitelist_sandbox["local_settings"].parent.mkdir(parents=True, exist_ok=True)
        existing = {
            "permissions": {
                "allow": ["Bash(git status)", "WebFetch(domain:example.com)"]
            }
        }
        whitelist_sandbox["local_settings"].write_text(json.dumps(existing))

        run_whitelist(whitelist_sandbox)

        settings = read_settings(whitelist_sandbox["local_settings"])
        allow = settings["permissions"]["allow"]
        assert "Bash(git status)" in allow
        assert "WebFetch(domain:example.com)" in allow
        for perm in EXPECTED_PERMISSIONS:
            assert perm in allow

    def test_preserves_existing_global_settings_keys(self, whitelist_sandbox):
        whitelist_sandbox["global_settings"].parent.mkdir(parents=True, exist_ok=True)
        existing = {
            "env": {"SOME_VAR": "value"},
            "permissions": {"allow": ["Bash(echo hello)"]},
        }
        whitelist_sandbox["global_settings"].write_text(json.dumps(existing))

        run_whitelist(whitelist_sandbox)

        settings = read_settings(whitelist_sandbox["global_settings"])
        assert settings["env"]["SOME_VAR"] == "value"
        assert "Bash(echo hello)" in settings["permissions"]["allow"]
        for perm in EXPECTED_PERMISSIONS:
            assert perm in settings["permissions"]["allow"]

    def test_creates_permissions_key_if_missing(self, whitelist_sandbox):
        whitelist_sandbox["global_settings"].parent.mkdir(parents=True, exist_ok=True)
        whitelist_sandbox["global_settings"].write_text(json.dumps({"env": {"A": "B"}}))

        run_whitelist(whitelist_sandbox)

        settings = read_settings(whitelist_sandbox["global_settings"])
        assert settings["env"]["A"] == "B"
        for perm in EXPECTED_PERMISSIONS:
            assert perm in settings["permissions"]["allow"]


# =============================================================================
# Idempotency
# =============================================================================


class TestIdempotency:
    """Verify running the script multiple times produces consistent results."""

    def test_permissions_not_duplicated(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox)
        run_whitelist(whitelist_sandbox)
        run_whitelist(whitelist_sandbox)

        settings = read_settings(whitelist_sandbox["local_settings"])
        allow = settings["permissions"]["allow"]
        for perm in EXPECTED_PERMISSIONS:
            assert allow.count(perm) == 1, f"Duplicate entry: {perm}"

    def test_recipient_idempotent(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "+15551234567")
        result = run_whitelist(whitelist_sandbox, "+15551234567")
        assert "already set to" in result.stdout
        assert get_recipient(whitelist_sandbox["send_sh"]) == "+15551234567"

    def test_second_run_reports_all_present(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox)
        result = run_whitelist(whitelist_sandbox)
        assert "all entries already present" in result.stdout


# =============================================================================
# RECIPIENT Update Consistency
# =============================================================================


class TestRecipientConsistency:
    """Verify send.sh and read.sh always have matching RECIPIENT values."""

    def test_both_files_updated_phone(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "555-867-5309")
        assert get_recipient(whitelist_sandbox["send_sh"]) == get_recipient(
            whitelist_sandbox["read_sh"]
        )

    def test_both_files_updated_email(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "test@example.com")
        assert get_recipient(whitelist_sandbox["send_sh"]) == get_recipient(
            whitelist_sandbox["read_sh"]
        )

    def test_overwrite_previous_recipient(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "old@example.com")
        assert get_recipient(whitelist_sandbox["send_sh"]) == "old@example.com"

        run_whitelist(whitelist_sandbox, "new@example.com")
        assert get_recipient(whitelist_sandbox["send_sh"]) == "new@example.com"
        assert get_recipient(whitelist_sandbox["read_sh"]) == "new@example.com"

    def test_switch_phone_to_email(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "+15551234567")
        assert get_recipient(whitelist_sandbox["send_sh"]) == "+15551234567"

        run_whitelist(whitelist_sandbox, "me@icloud.com")
        assert get_recipient(whitelist_sandbox["send_sh"]) == "me@icloud.com"
        assert get_recipient(whitelist_sandbox["read_sh"]) == "me@icloud.com"


# =============================================================================
# No-Argument Mode (permissions only)
# =============================================================================


class TestNoArgument:
    """Verify the script works without a phone/email argument."""

    def test_no_arg_skips_recipient(self, whitelist_sandbox):
        original = get_recipient(whitelist_sandbox["send_sh"])
        run_whitelist(whitelist_sandbox)
        assert get_recipient(whitelist_sandbox["send_sh"]) == original

    def test_no_arg_still_injects_permissions(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox)
        settings = read_settings(whitelist_sandbox["local_settings"])
        for perm in EXPECTED_PERMISSIONS:
            assert perm in settings["permissions"]["allow"]


# =============================================================================
# Combined Phone + Permissions
# =============================================================================


class TestCombinedSetup:
    """Verify phone configuration and permission injection work together."""

    def test_phone_and_permissions_in_one_call(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox, "1-555-867-5309")

        # Phone configured
        assert get_recipient(whitelist_sandbox["send_sh"]) == "+15558675309"
        assert get_recipient(whitelist_sandbox["read_sh"]) == "+15558675309"

        # Permissions injected
        local = read_settings(whitelist_sandbox["local_settings"])
        for perm in EXPECTED_PERMISSIONS:
            assert perm in local["permissions"]["allow"]

        global_ = read_settings(whitelist_sandbox["global_settings"])
        for perm in EXPECTED_PERMISSIONS:
            assert perm in global_["permissions"]["allow"]


# =============================================================================
# Alias Configuration
# =============================================================================


class TestAliasConfiguration:
    """Verify --aliases flag configures RECIPIENT_ALIASES in read.sh."""

    def test_aliases_set_in_read_sh(self, whitelist_sandbox):
        run_whitelist(
            whitelist_sandbox,
            "user@example.com",
            "--aliases",
            "+13522339160 noelnosse@gmail.com",
        )
        aliases = get_aliases(whitelist_sandbox["read_sh"])
        assert "+13522339160" in aliases
        assert "noelnosse@gmail.com" in aliases

    def test_aliases_not_in_send_sh(self, whitelist_sandbox):
        """send.sh should NOT have RECIPIENT_ALIASES — it sends to one address."""
        run_whitelist(
            whitelist_sandbox,
            "user@example.com",
            "--aliases",
            "+13522339160",
        )
        content = whitelist_sandbox["send_sh"].read_text()
        assert "RECIPIENT_ALIASES" not in content

    def test_aliases_with_phone_and_email_mix(self, whitelist_sandbox):
        run_whitelist(
            whitelist_sandbox,
            "+15551234567",
            "--aliases",
            "user@icloud.com nnosse@wgu.edu +13522339160",
        )
        aliases = get_aliases(whitelist_sandbox["read_sh"])
        assert "user@icloud.com" in aliases
        assert "nnosse@wgu.edu" in aliases
        assert "+13522339160" in aliases

    def test_aliases_overwrite_previous(self, whitelist_sandbox):
        run_whitelist(
            whitelist_sandbox,
            "user@example.com",
            "--aliases",
            "old@example.com",
        )
        assert "old@example.com" in get_aliases(whitelist_sandbox["read_sh"])

        run_whitelist(
            whitelist_sandbox,
            "user@example.com",
            "--aliases",
            "new@example.com",
        )
        aliases = get_aliases(whitelist_sandbox["read_sh"])
        assert "new@example.com" in aliases
        assert "old@example.com" not in aliases

    def test_aliases_idempotent(self, whitelist_sandbox):
        for _ in range(3):
            run_whitelist(
                whitelist_sandbox,
                "user@example.com",
                "--aliases",
                "+13522339160",
            )
        aliases = get_aliases(whitelist_sandbox["read_sh"])
        # Should appear exactly once, not duplicated
        assert aliases.count("+13522339160") == 1

    def test_no_aliases_leaves_empty(self, whitelist_sandbox):
        """Running without --aliases preserves the empty default."""
        run_whitelist(whitelist_sandbox, "user@example.com")
        aliases = get_aliases(whitelist_sandbox["read_sh"])
        assert aliases == ""

    def test_recipient_and_aliases_together(self, whitelist_sandbox):
        """Recipient and aliases are configured in one call."""
        run_whitelist(
            whitelist_sandbox,
            "nnosse@wgu.edu",
            "--aliases",
            "+13522339160 noelnosse@gmail.com",
        )
        assert get_recipient(whitelist_sandbox["send_sh"]) == "nnosse@wgu.edu"
        assert get_recipient(whitelist_sandbox["read_sh"]) == "nnosse@wgu.edu"
        aliases = get_aliases(whitelist_sandbox["read_sh"])
        assert "+13522339160" in aliases
        assert "noelnosse@gmail.com" in aliases


# =============================================================================
# Absolute Path Permissions (Option B — sub-agent defense-in-depth)
# =============================================================================


class TestAbsolutePathPermissions:
    """Verify absolute-path permission variants are injected alongside tilde versions.

    Sub-agents may not resolve ~ correctly, so whitelist_commands.sh must inject
    both ~/.claude/... and $HOME/.claude/... permission patterns.
    """

    def test_local_settings_has_absolute_permissions(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox)
        settings = read_settings(whitelist_sandbox["local_settings"])
        abs_perms = expected_absolute_permissions(str(whitelist_sandbox["home"]))
        for perm in abs_perms:
            assert perm in settings["permissions"]["allow"], (
                f"Missing absolute-path permission: {perm}"
            )

    def test_global_settings_has_absolute_permissions(self, whitelist_sandbox):
        run_whitelist(whitelist_sandbox)
        settings = read_settings(whitelist_sandbox["global_settings"])
        abs_perms = expected_absolute_permissions(str(whitelist_sandbox["home"]))
        for perm in abs_perms:
            assert perm in settings["permissions"]["allow"], (
                f"Missing absolute-path permission: {perm}"
            )

    def test_both_tilde_and_absolute_present(self, whitelist_sandbox):
        """Both tilde and absolute versions coexist in the allow list."""
        run_whitelist(whitelist_sandbox)
        settings = read_settings(whitelist_sandbox["local_settings"])
        allow = settings["permissions"]["allow"]
        abs_perms = expected_absolute_permissions(str(whitelist_sandbox["home"]))
        for tilde_perm, abs_perm in zip(EXPECTED_PERMISSIONS, abs_perms):
            assert tilde_perm in allow, f"Missing tilde permission: {tilde_perm}"
            assert abs_perm in allow, f"Missing absolute permission: {abs_perm}"

    def test_absolute_permissions_not_duplicated(self, whitelist_sandbox):
        """Running multiple times does not duplicate absolute-path entries."""
        run_whitelist(whitelist_sandbox)
        run_whitelist(whitelist_sandbox)
        run_whitelist(whitelist_sandbox)
        settings = read_settings(whitelist_sandbox["local_settings"])
        allow = settings["permissions"]["allow"]
        abs_perms = expected_absolute_permissions(str(whitelist_sandbox["home"]))
        for perm in abs_perms:
            assert allow.count(perm) == 1, f"Duplicate absolute entry: {perm}"

    def test_absolute_paths_use_real_home(self, whitelist_sandbox):
        """Absolute paths use $HOME, not a literal tilde."""
        run_whitelist(whitelist_sandbox)
        settings = read_settings(whitelist_sandbox["global_settings"])
        abs_perms = expected_absolute_permissions(str(whitelist_sandbox["home"]))
        for perm in abs_perms:
            assert "~" not in perm, f"Absolute perm should not contain tilde: {perm}"
            assert str(whitelist_sandbox["home"]) in perm
